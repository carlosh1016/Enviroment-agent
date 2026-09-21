import uuid

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from sqlalchemy import bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.logging_config import get_logger
from app.models.conversation import Conversation, Message, MessageRole
from app.models.document import Document, DocumentChunk
from app.models.tenant import Tenant
from app.services import openrouter_client
from app.services.ingestion_service import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    _embed_batch_with_retry,
)

logger = get_logger(__name__)

# "google/gemini-3.8-flash" (mas capaz) quema tokens de "reasoning" oculto antes de emitir
# contenido visible y puede devolver texto vacio si max_tokens no alcanza para ambos (verificado
# en vivo). Se usa el mismo modelo chico/predecible que ya usa ingestion_service para el chat.
CHAT_MODEL = "google/gemini-3.5-flash-lite"
OPENROUTER_MAX_TOKENS = 2048

BASE_TENANT_SLUG = "_base"
HISTORY_MESSAGE_LIMIT = 10
SCORE_THRESHOLD = 0.75
TITLE_MAX_WORDS = 6

SYSTEM_PROMPT = (
    "Eres un asistente legal especializado en normativa ambiental colombiana. Respondes "
    "preguntas sobre el Decreto 1076 de 2015 y sus resoluciones complementarias.\n"
    "REGLAS:\n"
    "- Fundamenta SIEMPRE tus respuestas en los fragmentos normativos proporcionados\n"
    "- Cita la fuente exacta: nombre del documento y numero de articulo\n"
    "- Si la informacion no esta en los fragmentos, dilo explicitamente\n"
    "- Mantén el hilo de la conversacion usando el historial previo\n"
    "- Responde en español, en tono formal pero claro"
)

TITLE_SYSTEM_PROMPT = (
    f"Genera un titulo corto (maximo {TITLE_MAX_WORDS} palabras) para una conversacion que "
    "empieza con el siguiente mensaje de un usuario. Devuelve SOLO el titulo, sin comillas "
    "ni puntuacion final, sin explicaciones ni texto adicional."
)

FALLBACK_MESSAGE = (
    "No encontré información relevante en el corpus normativo para tu pregunta. "
    "¿Podrías reformularla o ser más específico?"
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


async def _embed_query(query: str) -> list[float]:
    """Genera el embedding de una query reutilizando EXACTAMENTE la misma logica (semaforo
    global y retry con backoff ante 429) que usa ingestion_service.embed_chunks, en vez de
    duplicarla."""
    embedder = GoogleGenerativeAIEmbeddings(
        model=EMBEDDING_MODEL,
        google_api_key=settings.GOOGLE_API_KEY,
        output_dimensionality=EMBEDDING_DIMENSIONS,
    )
    vectors = await _embed_batch_with_retry(embedder, [query])
    return vectors[0]


async def retrieve_relevant_chunks(
    db: AsyncSession, query: str, tenant_id: uuid.UUID, top_k: int = 5
) -> list[dict]:
    """Recupera los chunks mas relevantes por similitud coseno, del tenant actual y del corpus
    base (_base) compartido. El filtro por tenant_id garantiza que nunca se cruzan datos entre
    tenants distintos.

    Devuelve una lista de dicts (content, score, document_id, chunk_index, numero_articulo,
    pagina_origen), solo con los chunks cuyo score de similitud supere SCORE_THRESHOLD. Lista
    vacia si ninguno lo supera.
    """
    base_tenant_id = await _get_base_tenant_id(db)
    tenant_ids = [tid for tid in (tenant_id, base_tenant_id) if tid is not None]
    dialect_name = db.bind.dialect.name if db.bind is not None else "postgresql"

    if dialect_name != "postgresql":
        # pgvector no esta disponible en SQLite (tests): se filtra solo por tenant, sin ranking
        # real por similitud (se asume score maximo para poder probar el flujo sin Postgres).
        result = await db.execute(
            select(DocumentChunk)
            .where(DocumentChunk.tenant_id.in_(tenant_ids))
            .order_by(DocumentChunk.chunk_index)
            .limit(top_k)
        )
        candidates = [
            {
                "content": chunk.content,
                "score": 1.0,
                "document_id": chunk.document_id,
                "chunk_index": chunk.chunk_index,
                "metadata_": chunk.metadata_ or {},
            }
            for chunk in result.scalars().all()
        ]
    else:
        query_vector = await _embed_query(query)
        vector_literal = "[" + ",".join(f"{v:.8f}" for v in query_vector) + "]"

        stmt = text(
            """
            SELECT content, document_id, chunk_index, metadata_,
                   1 - (embedding <=> CAST(:query_embedding AS vector)) AS score
            FROM document_chunks
            WHERE (tenant_id = :tenant_id OR tenant_id = :base_tenant_id)
            ORDER BY embedding <=> CAST(:query_embedding AS vector)
            LIMIT :k
            """
        ).bindparams(
            bindparam("tenant_id", value=tenant_id),
            bindparam("base_tenant_id", value=base_tenant_id),
            bindparam("query_embedding", value=vector_literal),
            bindparam("k", value=top_k),
        )
        result = await db.execute(stmt)
        candidates = [
            {
                "content": row["content"],
                "score": float(row["score"]),
                "document_id": row["document_id"],
                "chunk_index": row["chunk_index"],
                "metadata_": row["metadata_"] or {},
            }
            for row in result.mappings().all()
        ]

    return [
        {
            "content": c["content"],
            "score": c["score"],
            "document_id": c["document_id"],
            "chunk_index": c["chunk_index"],
            "numero_articulo": c["metadata_"].get("numero_articulo"),
            "pagina_origen": c["metadata_"].get("pagina_origen"),
        }
        for c in candidates
        if c["score"] > SCORE_THRESHOLD
    ]


async def generate_response(
    query: str, chunks: list[dict], history: list[Message], model: str = CHAT_MODEL
) -> str:
    """Genera la respuesta del agente via OpenRouter, basandose en los chunks recuperados y el
    historial de la conversacion (los ultimos HISTORY_MESSAGE_LIMIT mensajes).

    Cada dict de `chunks` debe incluir "document_name" (agregado por el llamador, ver chat())
    ademas de los campos de retrieve_relevant_chunks, para poder citar la fuente.
    """
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    if chunks:
        context_text = "\n\n".join(
            "[Fuente: {document_name}{articulo}]\n{content}".format(
                document_name=chunk.get("document_name", "desconocido"),
                articulo=f" - Articulo {chunk['numero_articulo']}" if chunk.get("numero_articulo") else "",
                content=chunk["content"],
            )
            for chunk in chunks
        )
        messages.append({"role": "system", "content": f"Fragmentos normativos relevantes:\n\n{context_text}"})

    for msg in history[-HISTORY_MESSAGE_LIMIT:]:
        role = "user" if msg.role == MessageRole.USER else "assistant"
        messages.append({"role": role, "content": msg.content})

    messages.append({"role": "user", "content": query})

    return await openrouter_client.chat_completion(messages, model=model, max_tokens=OPENROUTER_MAX_TOKENS)


async def _generate_session_title(first_message: str) -> str:
    """Genera un titulo corto para la conversacion a partir de su primer mensaje, via OpenRouter."""
    messages = [
        {"role": "system", "content": TITLE_SYSTEM_PROMPT},
        {"role": "user", "content": first_message},
    ]
    title = await openrouter_client.chat_completion(messages, model=CHAT_MODEL, max_tokens=32)
    return title.strip().strip('"').strip("'")


async def chat(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    user_message: str,
    tenant_id: uuid.UUID,
    user_message_id: uuid.UUID,
) -> Message:
    """Orquesta el flujo del agente: recupera contexto, genera respuesta y persiste el mensaje
    del assistant. Si no hay chunks relevantes (score > SCORE_THRESHOLD), responde con un
    mensaje de fallback sin llamar a generate_response.

    El mensaje del usuario (user_message_id) ya fue guardado por el router antes de llamar aqui,
    para que no se pierda si el RAG falla; se excluye del historial porque se envia aparte como
    la pregunta actual. Guarda en el Message del assistant los source_chunks (documento, chunk,
    score y ubicacion normativa) usados como contexto.

    Si el titulo de la conversacion es NULL, lo genera automaticamente a partir de este mensaje;
    un fallo generando el titulo no debe tumbar la respuesta del agente.
    """
    history_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.id != user_message_id)
        .order_by(Message.created_at.desc())
        .limit(HISTORY_MESSAGE_LIMIT)
    )
    history = list(reversed(history_result.scalars().all()))

    relevant_chunks = await retrieve_relevant_chunks(db, user_message, tenant_id)

    if not relevant_chunks:
        response_text = FALLBACK_MESSAGE
        sources: list[dict] = []
    else:
        document_ids = {chunk["document_id"] for chunk in relevant_chunks}
        filenames = await _get_document_filenames(db, document_ids)
        chunks_for_prompt = [
            {**chunk, "document_name": filenames.get(chunk["document_id"], "desconocido")}
            for chunk in relevant_chunks
        ]

        response_text = await generate_response(user_message, chunks_for_prompt, history, CHAT_MODEL)

        sources = [
            {
                "document_id": str(chunk["document_id"]),
                "chunk_index": chunk["chunk_index"],
                "score": chunk["score"],
                "numero_articulo": chunk["numero_articulo"],
                "pagina_origen": chunk["pagina_origen"],
            }
            for chunk in relevant_chunks
        ]

    assistant_msg = Message(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        role=MessageRole.ASSISTANT,
        content=response_text,
        source_chunks=sources,
    )
    db.add(assistant_msg)

    conversation = await db.get(Conversation, conversation_id)
    if conversation is not None and conversation.title is None:
        try:
            conversation.title = await _generate_session_title(user_message)
        except Exception:
            logger.warning("No se pudo generar el titulo automatico de la conversacion")

    await db.commit()
    await db.refresh(assistant_msg)

    return assistant_msg
