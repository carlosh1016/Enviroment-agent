import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_tenant, get_current_user
from app.logging_config import get_logger
from app.models.project import Project
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas import success_response
from app.schemas.project import PaginatedProjects, ProjectCreate, ProjectRead, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])
logger = get_logger(__name__)


async def _get_tenant_project_or_404(db: AsyncSession, project_id: uuid.UUID, tenant_id: uuid.UUID) -> Project:
    """Obtiene un proyecto por id, validando que pertenezca al tenant actual. Lanza 404 en caso contrario."""
    result = await db.execute(select(Project).where(Project.id == project_id, Project.tenant_id == tenant_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")
    return project


@router.get("/")
async def list_projects(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Lista los proyectos activos del tenant actual, con paginacion."""
    base_query = select(Project).where(Project.tenant_id == tenant.id, Project.is_active.is_(True))

    count_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = count_result.scalar_one()

    result = await db.execute(
        base_query.order_by(Project.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    projects = result.scalars().all()

    data = PaginatedProjects(
        items=[ProjectRead.model_validate(project) for project in projects],
        total=total,
        page=page,
        page_size=page_size,
    )
    return success_response(data=data.model_dump(mode="json"), message="Proyectos obtenidos exitosamente")


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
):
    """Crea un nuevo proyecto de estudio de suelos para el tenant actual, asignando created_by."""
    project = Project(**payload.model_dump(), tenant_id=tenant.id, created_by=current_user.id)
    db.add(project)
    await db.commit()
    await db.refresh(project)

    logger.info("Proyecto creado exitosamente")
    return success_response(
        data=ProjectRead.model_validate(project).model_dump(mode="json"),
        message="Proyecto creado exitosamente",
    )


@router.get("/{project_id}")
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Obtiene un proyecto por id, validando que pertenece al tenant actual."""
    project = await _get_tenant_project_or_404(db, project_id, tenant.id)
    return success_response(
        data=ProjectRead.model_validate(project).model_dump(mode="json"),
        message="Proyecto obtenido exitosamente",
    )


@router.patch("/{project_id}")
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Actualiza campos de un proyecto existente, validando que pertenece al tenant actual."""
    project = await _get_tenant_project_or_404(db, project_id, tenant.id)

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(project, field, value)

    await db.commit()
    await db.refresh(project)

    return success_response(
        data=ProjectRead.model_validate(project).model_dump(mode="json"),
        message="Proyecto actualizado exitosamente",
    )


@router.delete("/{project_id}")
async def delete_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Elimina logicamente un proyecto (soft delete, is_active=false), sin borrarlo fisicamente."""
    project = await _get_tenant_project_or_404(db, project_id, tenant.id)
    project.is_active = False

    await db.commit()

    return success_response(data=None, message="Proyecto eliminado exitosamente")
