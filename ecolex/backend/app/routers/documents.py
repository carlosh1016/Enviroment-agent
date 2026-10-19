import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
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
from app.services.rag_service import _get_base_tenant_id

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])
logger = get_logger(__name__)

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024
ALLOWED_EXTENSIONS = {
    ".pdf": DocumentFileType.PDF,
    ".docx": DocumentFileType.DOCX,
    ".txt": DocumentFileType.TXT,
    ".mhtml": DocumentFileType.MHTML,
    ".mht": DocumentFileType.MHTML,
    ".html": DocumentFileType.HTML,
    ".htm": DocumentFileType.HTML,
    ".xlsx": DocumentFileType.XLSX,
    ".csv": DocumentFileType.CSV,
}

# Archivo original (bytes tal cual se subieron), guardado en disco solo para poder mostrarlo
# despues en el visor ("Ver documento" en las fuentes del chat) -- NO es la fuente de verdad
# del contenido, que sigue siendo document_chunks. Ruta relativa al cwd del proceso (/app en
# Docker, ver Dockerfile WORKDIR), dentro del volumen montado: persiste entre reinicios del
# contenedor. Documentos subidos ANTES de esta funcionalidad no tienen archivo aqui (ver
# get_document_file): solo se guardan desde este cambio en adelante.
STORAGE_DIR = Path("storage/documents")

CONTENT_TYPES = {
    DocumentFileType.PDF: "application/pdf",
    DocumentFileType.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    DocumentFileType.TXT: "text/plain",
    # MHTML/XLSX no se renderizan "inline" en una pestaña como el PDF (el navegador los
    # descarga en vez de mostrarlos) -- el Content-Type sigue siendo el correcto para que,
    # al descargarlos, el sistema operativo los abra con la aplicacion correcta.
    DocumentFileType.MHTML: "multipart/related",
    DocumentFileType.HTML: "text/html",
    DocumentFileType.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    DocumentFileType.CSV: "text/csv",
}


def _extension_for(file_type: DocumentFileType) -> str:
    """Extension de archivo (con punto) correspondiente a un DocumentFileType."""
    return next(ext for ext, ft in ALLOWED_EXTENSIONS.items() if ft == file_type)


def _storage_path(document_id: uuid.UUID, file_type: DocumentFileType) -> Path:
    return STORAGE_DIR / f"{document_id}{_extension_for(file_type)}"


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


async def _get_viewable_document_or_404(db: AsyncSession, document_id: uuid.UUID, tenant_id: uuid.UUID) -> Document:
    """Como _get_tenant_document_or_404, pero tambien permite el corpus base (_base) compartido:
    las fuentes citadas en el chat pueden venir de documentos propios o del corpus normativo
    comun, y en ambos casos el usuario debe poder abrir el original."""
    base_tenant_id = await _get_base_tenant_id(db)
    allowed_tenant_ids = [tid for tid in (tenant_id, base_tenant_id) if tid is not None]
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.tenant_id.in_(allowed_tenant_ids))
    )
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
            detail="El archivo supera el tamano maximo permitido de 50MB",
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

    storage_path = _storage_path(document.id, document.file_type)
    await asyncio.to_thread(storage_path.parent.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(storage_path.write_bytes, file_bytes)

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


@router.get("/{document_id}/file")
async def get_document_file(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Sirve el archivo original (PDF/DOCX/TXT) para visualizarlo, ej. al hacer click en una
    fuente citada en el chat. Permite tanto documentos propios del tenant como del corpus base
    compartido (ver _get_viewable_document_or_404).

    Excepcion intencional al envoltorio {success, message, data} de toda la API: el contenido
    es binario (mismo criterio que /reports/conversations/{id}, ver reports.py).
    """
    document = await _get_viewable_document_or_404(db, document_id, tenant.id)
    storage_path = _storage_path(document.id, document.file_type)

    if not await asyncio.to_thread(storage_path.is_file):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El archivo original no esta disponible (se subio antes de esta funcionalidad)",
        )

    return FileResponse(
        storage_path,
        media_type=CONTENT_TYPES[document.file_type],
        headers={"Content-Disposition": f'inline; filename="{document.filename}"'},
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
    storage_path = _storage_path(document.id, document.file_type)

    await db.delete(document)
    await db.commit()

    await asyncio.to_thread(storage_path.unlink, missing_ok=True)

    return success_response(data=None, message="Documento eliminado exitosamente")
