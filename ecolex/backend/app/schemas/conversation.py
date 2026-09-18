import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.conversation import MessageRole


class ConversationCreate(BaseModel):
    """Datos opcionales para crear una nueva conversacion."""

    title: str | None = None


class ConversationUpdate(BaseModel):
    """Nuevo titulo de una conversacion existente."""

    title: str = Field(min_length=1, max_length=255)


class ConversationRead(BaseModel):
    """Representacion de una conversacion retornada por la API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID | None
    title: str | None
    created_at: datetime
    updated_at: datetime


class PaginatedConversations(BaseModel):
    """Envoltorio de paginacion para el listado de conversaciones."""

    items: list[ConversationRead]
    total: int
    page: int
    page_size: int


class MessageCreate(BaseModel):
    """Contenido de un mensaje enviado por el usuario al agente."""

    content: str = Field(min_length=1)


class SourceChunkRead(BaseModel):
    """Referencia a un chunk fuente usado para generar una respuesta del asistente."""

    document_name: str
    chunk_index: int


class MessageRead(BaseModel):
    """Representacion de un mensaje (usuario o asistente) retornada por la API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: MessageRole
    content: str
    source_chunks: list[SourceChunkRead] | None
    created_at: datetime
