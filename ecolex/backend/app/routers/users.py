import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_tenant, get_current_user
from app.logging_config import get_logger
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.schemas import success_response
from app.schemas.users import PaginatedUsers, UserCreate, UserRead, UserUpdate
from app.services.auth_service import hash_password

router = APIRouter(prefix="/api/v1/users", tags=["users"])
logger = get_logger(__name__)


def _require_admin(current_user: User) -> None:
    """Valida que el usuario actual tenga rol admin. Lanza 403 en caso contrario."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Solo un administrador puede gestionar usuarios"
        )


async def _get_tenant_user_or_404(db: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID) -> User:
    """Obtiene un usuario por id, validando que pertenezca al tenant actual. Lanza 404 en caso contrario."""
    result = await db.execute(select(User).where(User.id == user_id, User.tenant_id == tenant_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    return user


@router.get("/")
async def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
):
    """Lista los usuarios del tenant actual, con paginacion. Requiere rol admin."""
    _require_admin(current_user)

    base_query = select(User).where(User.tenant_id == tenant.id)

    count_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = count_result.scalar_one()

    result = await db.execute(
        base_query.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    users = result.scalars().all()

    data = PaginatedUsers(
        items=[UserRead.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
    )
    return success_response(data=data.model_dump(mode="json"), message="Usuarios obtenidos exitosamente")


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
):
    """Crea un usuario nuevo dentro del tenant actual. Requiere rol admin; no permite crear admins."""
    _require_admin(current_user)

    if payload.role == UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No se pueden crear usuarios administradores desde esta API",
        )

    existing = await db.execute(select(User).where(User.tenant_id == tenant.id, User.email == payload.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Ya existe un usuario con ese correo en esta organizacion"
        )

    user = User(
        tenant_id=tenant.id,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info("Usuario creado exitosamente")
    return success_response(
        data=UserRead.model_validate(user).model_dump(mode="json"), message="Usuario creado exitosamente"
    )


@router.patch("/{user_id}")
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
):
    """Actualiza el rol y/o el estado activo de un usuario del tenant. Requiere rol admin."""
    _require_admin(current_user)

    if user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No puede modificar su propio usuario")

    user = await _get_tenant_user_or_404(db, user_id, tenant.id)

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)

    return success_response(
        data=UserRead.model_validate(user).model_dump(mode="json"), message="Usuario actualizado exitosamente"
    )


@router.delete("/{user_id}")
async def deactivate_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
):
    """Desactiva (soft delete) un usuario del tenant. Requiere rol admin."""
    _require_admin(current_user)

    if user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No puede desactivar su propio usuario")

    user = await _get_tenant_user_or_404(db, user_id, tenant.id)
    user.is_active = False
    await db.commit()

    return success_response(data=None, message="Usuario desactivado exitosamente")
