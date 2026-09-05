import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.project import ProjectStatus


class ProjectCreate(BaseModel):
    """Datos requeridos para crear un nuevo proyecto de estudio de suelos."""

    name: str = Field(min_length=2, max_length=255)
    location_name: str | None = None
    municipality: str | None = None
    department: str | None = None
    study_date: date | None = None
    status: ProjectStatus = ProjectStatus.DRAFT


class ProjectUpdate(BaseModel):
    """Campos opcionales para actualizar un proyecto existente."""

    name: str | None = Field(default=None, min_length=2, max_length=255)
    location_name: str | None = None
    municipality: str | None = None
    department: str | None = None
    study_date: date | None = None
    status: ProjectStatus | None = None


class ProjectRead(BaseModel):
    """Representacion de un proyecto retornada por la API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    created_by: uuid.UUID | None
    name: str
    location_name: str | None
    municipality: str | None
    department: str | None
    study_date: date | None
    status: ProjectStatus
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PaginatedProjects(BaseModel):
    """Envoltorio de paginacion para el listado de proyectos."""

    items: list[ProjectRead]
    total: int
    page: int
    page_size: int
