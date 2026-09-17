import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


class RegisterRequest(BaseModel):
    """Datos requeridos para registrar una nueva organizacion (tenant) y su usuario administrador."""

    tenant_name: str = Field(min_length=2, max_length=255)
    tenant_slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    admin_email: EmailStr
    admin_password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    """Credenciales para iniciar sesion. tenant_slug es opcional para desambiguar emails compartidos."""

    email: EmailStr
    password: str
    tenant_slug: str | None = None


class UserRead(BaseModel):
    """Representacion de un usuario retornada por la API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    email: EmailStr
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    """Respuesta de login/refresh: el access token viaja en el cuerpo de la respuesta."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
