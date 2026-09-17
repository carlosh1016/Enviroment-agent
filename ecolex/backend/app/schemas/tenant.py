import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TenantBase(BaseModel):
    """Campos base compartidos de un tenant."""

    name: str
    slug: str


class TenantRead(BaseModel):
    """Representacion de un tenant retornada por la API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
