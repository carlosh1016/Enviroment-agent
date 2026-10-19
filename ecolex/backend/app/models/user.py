import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import GUID, Base


class UserRole(str, enum.Enum):
    """Roles disponibles para un usuario dentro de su organizacion (tenant)."""

    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


class User(Base):
    """Usuario de la plataforma, siempre asociado a un unico tenant."""

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=UserRole.VIEWER,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # True cuando un admin crea el usuario con una contrasena asignada por el (UserCreate.password
    # en routers/users.py): el frontend lo fuerza a definir una propia antes de usar el resto de
    # la app (ver AppShell). False para el admin que se auto-registra (eligio su propia clave) y
    # para cualquiera que ya la cambio o la reseteo (auth_service.change_password/reset_password).
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Recuperacion de contrasena (ver auth_service.request_password_reset/reset_password):
    # hash SHA-256 (no bcrypt) del token de un solo uso vigente, y su expiracion. Un unico
    # token activo a la vez por usuario (generar uno nuevo invalida cualquier anterior).
    reset_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reset_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    tenant = relationship("Tenant", back_populates="users")
