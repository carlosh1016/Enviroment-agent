import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.document import DocumentFileType, DocumentStatus


class DocumentRead(BaseModel):
    """Representacion de un documento retornada por la API, incluyendo su estado de procesamiento."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    uploaded_by: uuid.UUID | None
    filename: str
    file_type: DocumentFileType
    file_size_bytes: int
    status: DocumentStatus
    error_message: str | None
    chunk_count: int
    is_base_corpus: bool
    created_at: datetime
    updated_at: datetime


class PaginatedDocuments(BaseModel):
    """Envoltorio de paginacion para el listado de documentos."""

    items: list[DocumentRead]
    total: int
    page: int
    page_size: int
