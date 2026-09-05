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
