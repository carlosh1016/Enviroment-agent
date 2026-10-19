import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.logging_config import get_logger
from app.models.tenant import Tenant
from app.models.user import User, UserRole

logger = get_logger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

PASSWORD_RESET_TOKEN_BYTES = 32
PASSWORD_RESET_EXPIRE_MINUTES = 30


class SlugAlreadyExistsError(Exception):
    """Se lanza cuando se intenta registrar un tenant con un slug ya existente."""


def hash_password(password: str) -> str:
    """Hashea una contrasena en texto plano usando bcrypt con cost factor 12."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica una contrasena en texto plano contra su hash bcrypt."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user: User) -> str:
    """Genera un JWT de acceso de corta duracion (30 minutos por defecto) para el usuario dado."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user.id),
        "tenant_id": str(user.tenant_id),
        "role": user.role.value,
        "type": "access",
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(user: User) -> str:
    """Genera un JWT de refresco de larga duracion (7 dias por defecto) para el usuario dado."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user.id),
        "tenant_id": str(user.tenant_id),
        "type": "refresh",
        "iat": now,
        "exp": expire,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_refresh_token(token: str) -> dict:
    """Decodifica y valida un refresh token JWT, verificando explicitamente su tipo."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise ValueError("Refresh token invalido o expirado")

    if payload.get("type") != "refresh":
        raise ValueError("Tipo de token invalido")

    return payload


async def authenticate_user(
    db: AsyncSession, email: str, password: str, tenant_slug: str | None = None
) -> User | None:
    """Valida credenciales de un usuario. Si se provee tenant_slug, restringe la busqueda a ese tenant."""
    query = select(User).join(Tenant, Tenant.id == User.tenant_id).where(User.email == email)
    if tenant_slug:
        query = query.where(Tenant.slug == tenant_slug)

    result = await db.execute(query)
    user = result.scalars().first()

    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


async def register_tenant_with_admin(
    db: AsyncSession,
    tenant_name: str,
    tenant_slug: str,
    admin_email: str,
    admin_password: str,
) -> tuple[Tenant, User]:
    """Crea un tenant y su primer usuario administrador en una unica transaccion atomica."""
    existing = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    if existing.scalar_one_or_none() is not None:
        raise SlugAlreadyExistsError("El slug de la organizacion ya esta en uso")

    tenant = Tenant(name=tenant_name, slug=tenant_slug)
    db.add(tenant)
    await db.flush()

    admin = User(
        tenant_id=tenant.id,
        email=admin_email,
        hashed_password=hash_password(admin_password),
        role=UserRole.ADMIN,
    )
    db.add(admin)
    await db.flush()
    await db.commit()
    await db.refresh(tenant)
    await db.refresh(admin)

    logger.info("Nuevo tenant registrado exitosamente")
    return tenant, admin


def _hash_reset_token(token: str) -> str:
    """Hash deterministico (SHA-256, no bcrypt) del token de reset.

    A diferencia de una contrasena, el token ya es aleatorio y de alta entropia
    (secrets.token_urlsafe), asi que no necesita un hash lento/salteado -- y necesita ser
    deterministico para poder buscarlo por igualdad en la base de datos (bcrypt genera un hash
    distinto cada vez incluso para el mismo input, lo cual haria imposible este lookup).
    """
    return hashlib.sha256(token.encode()).hexdigest()


def _is_expired(expires_at: datetime) -> bool:
    """Compara expires_at contra la hora actual, tolerando que venga naive (SQLite en tests no
    preserva tzinfo aunque la columna sea DateTime(timezone=True); siempre se escribe en UTC,
    asi que tratar un valor naive como UTC es correcto)."""
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at < datetime.now(timezone.utc)


async def request_password_reset(db: AsyncSession, email: str, tenant_slug: str | None = None) -> None:
    """Genera un token de reset de un solo uso (vigente PASSWORD_RESET_EXPIRE_MINUTES minutos) y
    lo registra en el log del servidor en vez de enviarlo por correo real: este proyecto no
    tiene un proveedor de email configurado. En un despliegue real, aqui iria la llamada a un
    servicio de email (ej. Resend, SES) con el link de reset, en vez del logger.

    SIEMPRE retorna sin error, exista o no el email/tenant_slug: revelar si una cuenta esta
    registrada permitiria enumerar usuarios validos, por eso el router responde el mismo
    mensaje generico sin importar lo que haga esta funcion.
    """
    query = select(User).join(Tenant, Tenant.id == User.tenant_id).where(User.email == email)
    if tenant_slug:
        query = query.where(Tenant.slug == tenant_slug)

    result = await db.execute(query)
    user = result.scalars().first()

    if user is None or not user.is_active:
        logger.info("Solicitud de reset de contrasena para un email no registrado o inactivo")
        return

    raw_token = secrets.token_urlsafe(PASSWORD_RESET_TOKEN_BYTES)
    user.reset_token_hash = _hash_reset_token(raw_token)
    user.reset_token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=PASSWORD_RESET_EXPIRE_MINUTES)
    await db.commit()

    # TODO produccion: reemplazar este log por un envio real de email con un link que incluya
    # este token (ej. https://app.ecolex.co/reset-password?token=<raw_token>).
    logger.info("Token de reset de contrasena generado (simulando envio de email): %s", raw_token)


async def reset_password(db: AsyncSession, token: str, new_password: str) -> bool:
    """Valida un token de reset (existente y no vencido) y actualiza la contrasena. El token se
    invalida de inmediato despues de usarse (de un solo uso). Retorna False si el token es
    invalido, ya se uso o vencio."""
    result = await db.execute(select(User).where(User.reset_token_hash == _hash_reset_token(token)))
    user = result.scalar_one_or_none()

    if user is None or user.reset_token_expires_at is None or _is_expired(user.reset_token_expires_at):
        return False

    user.hashed_password = hash_password(new_password)
    user.reset_token_hash = None
    user.reset_token_expires_at = None
    await db.commit()
    return True


async def change_password(db: AsyncSession, user: User, current_password: str, new_password: str) -> bool:
    """Cambia la contrasena de un usuario ya autenticado, validando primero la contrasena
    actual. Retorna False si la contrasena actual no coincide."""
    if not verify_password(current_password, user.hashed_password):
        return False
    user.hashed_password = hash_password(new_password)
    await db.commit()
    return True
