from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.limiter import limiter
from app.logging_config import get_logger
from app.models.user import User
from app.schemas import success_response
from app.schemas.user import LoginRequest, RegisterRequest, TokenResponse, UserRead
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger(__name__)


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """Establece el refresh token como cookie httpOnly, con flags Secure y SameSite=strict."""
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="strict",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/auth",
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Crea un nuevo tenant y su primer usuario administrador en una unica transaccion atomica."""
    try:
        tenant, admin = await auth_service.register_tenant_with_admin(
            db,
            tenant_name=payload.tenant_name,
            tenant_slug=payload.tenant_slug,
            admin_email=payload.admin_email,
            admin_password=payload.admin_password,
        )
    except auth_service.SlugAlreadyExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    return success_response(
        data={
            "tenant": {"id": str(tenant.id), "name": tenant.name, "slug": tenant.slug},
            "user": UserRead.model_validate(admin).model_dump(mode="json"),
        },
        message="Organizacion y usuario administrador creados exitosamente",
    )


@router.post("/login")
@limiter.limit(settings.RATE_LIMIT_LOGIN)
async def login(
    request: Request,
    response: Response,
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Autentica un usuario. Retorna el access token en el cuerpo y el refresh token en cookie httpOnly."""
    user = await auth_service.authenticate_user(db, payload.email, payload.password, payload.tenant_slug)
    if user is None:
        logger.warning("Intento de login fallido")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales invalidas")

    access_token = auth_service.create_access_token(user)
    refresh_token = auth_service.create_refresh_token(user)
    _set_refresh_cookie(response, refresh_token)

    token_data = TokenResponse(
        access_token=access_token, expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    return success_response(data=token_data.model_dump(), message="Inicio de sesion exitoso")


@router.post("/refresh")
async def refresh(
    response: Response,
    db: AsyncSession = Depends(get_db),
    refresh_token: str | None = Cookie(default=None, alias=settings.REFRESH_COOKIE_NAME),
):
    """Emite un nuevo access token a partir de la cookie de refresh, rotando el refresh token."""
    if refresh_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token no encontrado")

    try:
        payload = auth_service.decode_refresh_token(refresh_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    result = await db.execute(
        select(User).where(User.id == payload.get("sub"), User.tenant_id == payload.get("tenant_id"))
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado o inactivo")

    new_access_token = auth_service.create_access_token(user)
    new_refresh_token = auth_service.create_refresh_token(user)
    _set_refresh_cookie(response, new_refresh_token)

    token_data = TokenResponse(
        access_token=new_access_token, expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    return success_response(data=token_data.model_dump(), message="Token renovado exitosamente")


@router.post("/logout")
async def logout(response: Response):
    """Invalida la sesion del usuario eliminando la cookie de refresh token."""
    response.delete_cookie(key=settings.REFRESH_COOKIE_NAME, path="/auth")
    return success_response(data=None, message="Sesion cerrada exitosamente")


@router.get("/me")
async def me(current_user: User = Depends(get_current_user)):
    """Retorna los datos del usuario autenticado actual."""
    return success_response(
        data=UserRead.model_validate(current_user).model_dump(mode="json"),
        message="Usuario actual obtenido exitosamente",
    )
