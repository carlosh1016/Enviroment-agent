import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


class UserRead(BaseModel):
    """Representacion de un usuario del tenant, para el modulo de gestion de usuarios."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    role: UserRole
    is_active: bool
    created_at: datetime


class PaginatedUsers(BaseModel):
    """Envoltorio de paginacion para el listado de usuarios del tenant."""

    items: list[UserRead]
    total: int
    page: int
    page_size: int


class UserCreate(BaseModel):
    """Datos requeridos para crear un usuario dentro del tenant actual. No permite rol admin."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: UserRole


class UserUpdate(BaseModel):
    """Campos editables de un usuario existente: rol y/o estado activo."""

    role: UserRole | None = None
    is_active: bool | None = None
