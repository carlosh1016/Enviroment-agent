import uuid

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from sqlalchemy import bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.logging_config import get_logger
from app.models.conversation import Message, MessageRole
from app.models.document import Document, DocumentChunk
from app.models.tenant import Tenant

logger = get_logger(__name__)

CHAT_MODEL = "gemini-2.0-flash"
EMBEDDING_MODEL = "models/text-embedding-004"
BASE_TENANT_SLUG = "_base"
HISTORY_MESSAGE_LIMIT = 6

SYSTEM_PROMPT = (
    "Eres un asistente legal ambiental especializado en normativa colombiana. "
    "Responde SOLO basandote en el contexto proporcionado. Si la informacion no esta "
    "en el contexto, di explicitamente que no tienes informacion suficiente. "
    "Cita la fuente (nombre del documento) cuando sea posible."
)


async def _get_base_tenant_id(db: AsyncSession) -> uuid.UUID | None:
    """Obtiene el id del tenant del sistema (_base) que contiene el corpus normativo compartido."""
    result = await db.execute(select(Tenant.id).where(Tenant.slug == BASE_TENANT_SLUG))
    return result.scalar_one_or_none()


async def _get_document_filenames(db: AsyncSession, document_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Obtiene en un solo query los nombres de archivo de un conjunto de documentos."""
    if not document_ids:
        return {}
    result = await db.execute(select(Document.id, Document.filename).where(Document.id.in_(document_ids)))
    return {doc_id: filename for doc_id, filename in result.all()}


async def retrieve_context(db: AsyncSession, query: str, tenant_id: uuid.UUID, k: int = 5) -> list[DocumentChunk]:
    """Recupera los k chunks mas relevantes por similitud coseno, del tenant actual y del corpus base.

    El filtro por tenant_id garantiza que nunca se cruzan datos entre tenants distintos: solo se
    incluyen chunks del tenant que consulta y los del tenant del sistema (slug='_base').
    """
    embedder = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL, google_api_key=settings.GOOGLE_API_KEY)
    query_vector = await embedder.aembed_query(query)

    base_tenant_id = await _get_base_tenant_id(db)
    dialect_name = db.bind.dialect.name if db.bind is not None else "postgresql"

    if dialect_name != "postgresql":
        # pgvector no esta disponible en SQLite (tests): se filtra solo por tenant, sin ranking por similitud real.
        tenant_ids = [tid for tid in (tenant_id, base_tenant_id) if tid is not None]
        result = await db.execute(
            select(DocumentChunk)
            .where(DocumentChunk.tenant_id.in_(tenant_ids))
            .order_by(DocumentChunk.chunk_index)
            .limit(k)
        )
        return list(result.scalars().all())

    vector_literal = "[" + ",".join(f"{v:.8f}" for v in query_vector) + "]"

    stmt = select(DocumentChunk).from_statement(
        text(
            """
            SELECT * FROM document_chunks
            WHERE (tenant_id = :tenant_id OR tenant_id = :base_tenant_id)
            ORDER BY embedding <=> CAST(:query_embedding AS vector)
            LIMIT :k
            """
        ).bindparams(
            bindparam("tenant_id", value=tenant_id),
            bindparam("base_tenant_id", value=base_tenant_id),
            bindparam("query_embedding", value=vector_literal),
            bindparam("k", value=k),
        )
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def generate_response(
    query: str, context_chunks: list[DocumentChunk], conversation_history: list[Message]
) -> str:
    """Genera la respuesta del agente con Gemini, basandose solo en el contexto recuperado."""
    if context_chunks:
        context_text = "\n\n".join(
            f"[Fuente: {getattr(chunk, '_document_filename', 'desconocido')}]\n{chunk.content}"
            for chunk in context_chunks
        )
    else:
        context_text = "No se encontro contexto relevante en la base de conocimiento."

    history_messages = []
    for msg in conversation_history[-HISTORY_MESSAGE_LIMIT:]:
        if msg.role == MessageRole.USER:
            history_messages.append(HumanMessage(content=msg.content))
        else:
            history_messages.append(AIMessage(content=msg.content))

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        SystemMessage(content=f"Contexto:\n{context_text}"),
        *history_messages,
        HumanMessage(content=query),
    ]

    llm = ChatGoogleGenerativeAI(model=CHAT_MODEL, google_api_key=settings.GOOGLE_API_KEY)
    response = await llm.ainvoke(messages)
    return response.content


async def chat(db: AsyncSession, conversation_id: uuid.UUID, user_message: str, tenant_id: uuid.UUID) -> Message:
    """Orquesta el flujo del agente: recupera contexto, genera respuesta y persiste ambos mensajes.

    Guarda en el Message del assistant los source_chunks (documento y chunk_index) usados como contexto.
    """
    history_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(HISTORY_MESSAGE_LIMIT)
    )
    history = list(reversed(history_result.scalars().all()))

    context_chunks = await retrieve_context(db, user_message, tenant_id)

    document_ids = {chunk.document_id for chunk in context_chunks}
    filenames = await _get_document_filenames(db, document_ids)
    for chunk in context_chunks:
        chunk._document_filename = filenames.get(chunk.document_id, "desconocido")

    response_text = await generate_response(user_message, context_chunks, history)

    user_msg = Message(
        tenant_id=tenant_id, conversation_id=conversation_id, role=MessageRole.USER, content=user_message
    )
    db.add(user_msg)

    source_chunks = [
        {
            "document_id": str(chunk.document_id),
            "document_name": filenames.get(chunk.document_id, "desconocido"),
            "chunk_index": chunk.chunk_index,
        }
        for chunk in context_chunks
    ]
    assistant_msg = Message(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        role=MessageRole.ASSISTANT,
        content=response_text,
        source_chunks=source_chunks,
    )
    db.add(assistant_msg)

    await db.commit()
    await db.refresh(assistant_msg)

    return assistant_msg
