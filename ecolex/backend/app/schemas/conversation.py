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
    # Poblado por el router (no es una columna de Conversation): email del dueno de la
    # conversacion. Siempre se incluye, aunque para un usuario no-admin viendo su propia lista
    # es simplemente su propio email -- no revela nada nuevo. Relevante quien SI importa cuando
    # un admin ve las conversaciones de todo el tenant (ver list_conversations).
    user_email: str | None = None
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
    """Referencia a un chunk fuente usado para generar una respuesta del asistente.

    Guarda solo la referencia (documento, chunk, score, ubicacion normativa), nunca el texto
    completo del chunk.
    """

    document_id: uuid.UUID
    # Opcional (default None): mensajes guardados ANTES de que chat() empezara a incluir
    # document_name en source_chunks (ver rag_service.chat()) no lo tienen. Si fuera
    # obligatorio, GET /conversations/{id}/messages revienta con un ValidationError al leer
    # cualquier conversacion vieja con fuentes -- bug real, detectado en produccion.
    document_name: str | None = None
    chunk_index: int
    score: float
    numero_articulo: str | None = None
    pagina_origen: int | None = None


class MessageRead(BaseModel):
    """Representacion de un mensaje (usuario o asistente) retornada por la API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: MessageRole
    content: str
    source_chunks: list[SourceChunkRead] | None
    created_at: datetime
