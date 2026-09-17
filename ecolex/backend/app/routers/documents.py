import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_tenant, get_current_user
from app.logging_config import get_logger
from app.models.document import Document, DocumentFileType, DocumentStatus
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.schemas import success_response
from app.schemas.document import DocumentRead, PaginatedDocuments
from app.services import ingestion_service

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])
logger = get_logger(__name__)

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf": DocumentFileType.PDF, ".docx": DocumentFileType.DOCX, ".txt": DocumentFileType.TXT}


def _require_upload_role(current_user: User) -> None:
    """Valida que el usuario tenga rol admin o analyst para subir documentos."""
    if current_user.role not in (UserRole.ADMIN, UserRole.ANALYST):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tiene permisos para subir documentos")


async def _get_tenant_document_or_404(db: AsyncSession, document_id: uuid.UUID, tenant_id: uuid.UUID) -> Document:
    """Obtiene un documento por id, validando que pertenezca al tenant actual. Lanza 404 en caso contrario."""
    result = await db.execute(select(Document).where(Document.id == document_id, Document.tenant_id == tenant_id))
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documento no encontrado")
    return document


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    es_base_corpus: bool = Form(default=False),
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
):
    """Sube un documento, lo registra en estado 'processing' y lanza el pipeline de ingesta en background.

    El cliente puede hacer polling a GET /documents/{id} para ver cuando status pasa a 'ready'.
    """
    _require_upload_role(current_user)

    filename = file.filename or "documento"
    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Extension de archivo no soportada. Solo se permiten .pdf, .docx y .txt",
        )

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El archivo supera el tamano maximo permitido de 10MB",
        )

    document = Document(
        tenant_id=tenant.id,
        uploaded_by=current_user.id,
        filename=filename,
        file_type=ALLOWED_EXTENSIONS[extension],
        file_size_bytes=len(file_bytes),
        status=DocumentStatus.PROCESSING,
        is_base_corpus=es_base_corpus,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    background_tasks.add_task(
        ingestion_service.process_document_background,
        document.id,
        file_bytes,
        ALLOWED_EXTENSIONS[extension].value,
        tenant.id,
    )

    logger.info("Documento recibido, procesamiento en background iniciado")
    return success_response(
        data=DocumentRead.model_validate(document).model_dump(mode="json"),
        message="Documento recibido, procesando en segundo plano",
    )


@router.get("/")
async def list_documents(
    status_filter: DocumentStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Lista los documentos del tenant actual. El corpus base compartido nunca aparece aqui."""
    base_query = select(Document).where(Document.tenant_id == tenant.id, Document.is_base_corpus.is_(False))
    if status_filter is not None:
        base_query = base_query.where(Document.status == status_filter)

    count_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = count_result.scalar_one()

    result = await db.execute(
        base_query.order_by(Document.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    documents = result.scalars().all()

    data = PaginatedDocuments(
        items=[DocumentRead.model_validate(doc) for doc in documents],
        total=total,
        page=page,
        page_size=page_size,
    )
    return success_response(data=data.model_dump(mode="json"), message="Documentos obtenidos exitosamente")


@router.get("/{document_id}")
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Obtiene el detalle y estado de procesamiento de un documento, validando que pertenece al tenant actual."""
    document = await _get_tenant_document_or_404(db, document_id, tenant.id)
    return success_response(
        data=DocumentRead.model_validate(document).model_dump(mode="json"),
        message="Documento obtenido exitosamente",
    )


@router.delete("/{document_id}")
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
):
    """Elimina permanentemente un documento y sus chunks asociados (CASCADE). Requiere rol admin."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Solo un administrador puede eliminar documentos"
        )

    document = await _get_tenant_document_or_404(db, document_id, tenant.id)
    await db.delete(document)
    await db.commit()

    return success_response(data=None, message="Documento eliminado exitosamente")
