import asyncio
import re
import uuid

from sqlalchemy import bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging_config import get_logger
from app.models.conversation import Conversation, Message, MessageRole
from app.models.document import Document, DocumentChunk
from app.models.tenant import Tenant
from app.services import openrouter_client
from app.services.ingestion_service import _embed_batch

logger = get_logger(__name__)

# "google/gemini-3.8-flash" (mas capaz) quema tokens de "reasoning" oculto antes de emitir
# contenido visible y puede devolver texto vacio si max_tokens no alcanza para ambos (verificado
# en vivo). Se usa el mismo modelo chico/predecible que ya usa ingestion_service para el chat.
CHAT_MODEL = "google/gemini-3.5-flash-lite"
OPENROUTER_MAX_TOKENS = 2048

BASE_TENANT_SLUG = "_base"
HISTORY_MESSAGE_LIMIT = 10
# Calibrado empiricamente con qwen/qwen3-embedding-8b (ver CLAUDE.md): preguntas totalmente
# ajenas al corpus (ej. "receta de pasta") puntuan <=0.29; preguntas relevantes, 0.40-0.72.
# 0.75 (calibrado para Gemini) descartaba casi todo con el modelo nuevo.
SCORE_THRESHOLD = 0.45
TITLE_MAX_WORDS = 6

# Preguntas de tipo "que necesito para montar una fabrica de metalurgia?" tocan varios permisos
# a la vez (emisiones, vertimientos, residuos peligrosos, licenciamiento...), pero una sola
# busqueda por similitud textual solo trae lo mas parecido A LA PREGUNTA COMPLETA, no un chunk
# representativo de cada tema. _expand_query descompone la pregunta en sub-busquedas por tema
# para cubrir varios permisos en una misma respuesta (ver retrieve_relevant_chunks).
MAX_SUBQUERIES = 4
MAX_RELEVANT_CHUNKS = 10

SYSTEM_PROMPT = (
    "Eres el asistente de Ecolex: ayudas a personas de empresas colombianas a entender la "
    "normativa ambiental (Decreto 1076 de 2015 y sus resoluciones complementarias) sin tener "
    "que leerse el decreto completo.\n"
    "REGLAS:\n"
    "- Fundamenta SIEMPRE tus respuestas en los fragmentos normativos proporcionados\n"
    "- Cita la fuente exacta: nombre del documento y numero de articulo\n"
    "- Si la informacion no esta en los fragmentos, dilo explicitamente\n"
    "- Mantén el hilo de la conversacion usando el historial previo\n"
    "- Responde en español, con un tono cercano y conversacional, como si le explicaras el "
    "tema a un colega: directo, sin rodeos ni relleno innecesario, y sin sonar como un "
    "documento legal o un comunicado corporativo. Evita frases hechas de \"asistente formal\" "
    "(ej. \"estare encantado de ayudarte\", \"no dude en consultarme\"); ve directo al punto.\n"
    "- La precision tecnica y las citas NO son negociables: cercano en el tono, riguroso en el "
    "contenido\n"
    "- Puedes usar formato Markdown (negritas, listas, titulos cortos) cuando ayude a que la "
    "respuesta se entienda mejor. Si la pregunta implica comparar varias opciones, permisos o "
    "requisitos, usa una tabla Markdown (con encabezados `|---|---|`) en vez de un parrafo "
    "largo; para todo lo demas, prosa normal\n"
    "- Cada fragmento de contexto viene marcado como [Fuente N: ...]. Al final de tu respuesta "
    "(nunca antes, el usuario no vera esta linea), agrega una linea nueva con EXACTAMENTE este "
    "formato: `FUENTES: N,N,N` listando SOLO los numeros N de los fragmentos que de verdad "
    "usaste para construir la respuesta (no todos los que recibiste). Si no te basaste en "
    "ningun fragmento en particular, escribe `FUENTES: ninguna`"
)

# Marca interna que el LLM agrega al final de su respuesta (ver SYSTEM_PROMPT) para declarar
# cuales [Fuente N] realmente cito. Se parsea y se quita antes de mostrarle el texto al usuario;
# existe para que la UI solo muestre como "fuentes" las que de verdad informaron la respuesta,
# no las ~10 que se le pasaron de contexto (la mayoria, en un corpus normativo grande, suenan
# relevantes por similitud pero no son las que el modelo termino usando).
_SOURCES_FOOTER_RE = re.compile(r"^[ \t]*FUENTES:[ \t]*([^\n]*)[ \t]*\s*\Z", re.IGNORECASE | re.MULTILINE)

TITLE_SYSTEM_PROMPT = (
    f"Genera un titulo corto (maximo {TITLE_MAX_WORDS} palabras) para una conversacion que "
    "empieza con el siguiente mensaje de un usuario. Devuelve SOLO el titulo, sin comillas "
    "ni puntuacion final, sin explicaciones ni texto adicional."
)

FALLBACK_MESSAGE = (
    "No encontré información relevante en el corpus normativo para tu pregunta. "
    "¿Podrías reformularla o ser más específico?"
)

EXPANSION_SYSTEM_PROMPT = (
    "Eres un asistente que prepara busquedas sobre un corpus de normativa ambiental "
    "colombiana (Decreto 1076 de 2015 y sus resoluciones: vertimientos, emisiones "
    "atmosfericas, recurso hidrico, ruido, residuos peligrosos, licenciamiento ambiental, "
    "entre otros).\n"
    "Dada la pregunta de un usuario, identifica los distintos permisos o tramites "
    "ambientales que le aplicarian (por ejemplo, si pregunta por montar una actividad o "
    "empresa, piensa en TODOS los permisos que normalmente necesitaria: vertimientos, "
    "emisiones al aire, generacion de residuos peligrosos, concesion de aguas, licencia "
    "ambiental, etc.).\n"
    "Genera entre 1 y 4 busquedas cortas (una frase cada una), una por linea, sin numeracion "
    "ni guiones ni explicaciones, cada una enfocada en UN solo tema/permiso. Si la pregunta ya "
    "es puntual y trata un solo tema, genera una unica busqueda igual o muy similar a ella."
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
    """Genera el embedding de una query con el mismo modelo y semaforo que la ingesta."""
    vectors = await _embed_batch([query])
    return vectors[0]


async def _expand_query(query: str) -> list[str]:
    """Descompone la pregunta del usuario en sub-busquedas por tema/permiso ambiental (ver
    EXPANSION_SYSTEM_PROMPT), para que preguntas que abarcan varios permisos a la vez (ej. "que
    necesito para montar una fabrica de metalurgia?") puedan recuperar chunks de cada tema en
    vez de solo los mas parecidos a la pregunta completa.

    Es una mejora de recall, no un paso critico: si el LLM falla, retorna [] y el llamador cae
    de vuelta a buscar solo con la pregunta original.
    """
    try:
        raw = await openrouter_client.chat_completion(
            [
                {"role": "system", "content": EXPANSION_SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
            model=CHAT_MODEL,
            max_tokens=200,
        )
    except Exception:
        logger.warning("No se pudo expandir la consulta en sub-busquedas, se usara solo la original")
        return []

    subqueries = [line.strip("-*• \t") for line in raw.splitlines()]
    return [sub for sub in subqueries if sub][:MAX_SUBQUERIES]


async def retrieve_relevant_chunks(
    db: AsyncSession, query: str, tenant_id: uuid.UUID, top_k: int = 5
) -> list[dict]:
    """Recupera los chunks mas relevantes por similitud coseno, del tenant actual y del corpus
    base (_base) compartido. El filtro por tenant_id garantiza que nunca se cruzan datos entre
    tenants distintos.

    En Postgres, la pregunta se expande primero en sub-busquedas por tema (_expand_query) y se
    hace una busqueda vectorial por cada una (top_k resultados cada una); los resultados se
    combinan quedandose con el score mas alto por chunk, para poder cubrir preguntas que tocan
    varios permisos/temas a la vez sin que una sola busqueda por similitud textual aplaste a
    los temas menos parecidos a la pregunta completa.

    Devuelve una lista de hasta MAX_RELEVANT_CHUNKS dicts (content, score, document_id,
    chunk_index, numero_articulo, pagina_origen), ordenada por score descendente, solo con los
    chunks cuyo score supere SCORE_THRESHOLD. Lista vacia si ninguno lo supera.
    """
    base_tenant_id = await _get_base_tenant_id(db)
    tenant_ids = [tid for tid in (tenant_id, base_tenant_id) if tid is not None]
    dialect_name = db.bind.dialect.name if db.bind is not None else "postgresql"

    if dialect_name != "postgresql":
        # pgvector no esta disponible en SQLite (tests): se filtra solo por tenant, sin ranking
        # real por similitud (se asume score maximo para poder probar el flujo sin Postgres).
        # No hay expansion de query: sin similitud real, no aporta nada y solo gastaria llamadas.
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
        search_queries = [query]
        for subquery in await _expand_query(query):
            if subquery not in search_queries:
                search_queries.append(subquery)

        # Los embeddings de las sub-consultas se piden en paralelo: son llamadas HTTP a
        # OpenRouter independientes entre si y, en serie, los reintentos ante fallos de red
        # transitorios se acumulan (visto en vivo: >90s para 5 sub-consultas). Las busquedas en
        # Postgres si quedan en serie porque comparten la misma AsyncSession (no es seguro
        # ejecutar queries concurrentes sobre la misma sesion), pero son locales y rapidas.
        query_vectors = await asyncio.gather(*(_embed_query(sq) for sq in search_queries))

        best_by_chunk: dict[tuple[uuid.UUID, int], dict] = {}
        for query_vector in query_vectors:
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

            for row in result.mappings().all():
                key = (row["document_id"], row["chunk_index"])
                score = float(row["score"])
                if key not in best_by_chunk or score > best_by_chunk[key]["score"]:
                    best_by_chunk[key] = {
                        "content": row["content"],
                        "score": score,
                        "document_id": row["document_id"],
                        "chunk_index": row["chunk_index"],
                        "metadata_": row["metadata_"] or {},
                    }

        candidates = sorted(best_by_chunk.values(), key=lambda c: c["score"], reverse=True)

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
    ][:MAX_RELEVANT_CHUNKS]


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
            "[Fuente {n}: {document_name}{articulo}]\n{content}".format(
                n=i + 1,
                document_name=chunk.get("document_name", "desconocido"),
                articulo=f" - Articulo {chunk['numero_articulo']}" if chunk.get("numero_articulo") else "",
                content=chunk["content"],
            )
            for i, chunk in enumerate(chunks)
        )
        messages.append({"role": "system", "content": f"Fragmentos normativos relevantes:\n\n{context_text}"})

    for msg in history[-HISTORY_MESSAGE_LIMIT:]:
        role = "user" if msg.role == MessageRole.USER else "assistant"
        messages.append({"role": role, "content": msg.content})

    messages.append({"role": "user", "content": query})

    return await openrouter_client.chat_completion(messages, model=model, max_tokens=OPENROUTER_MAX_TOKENS)


def _extract_cited_sources(response_text: str, total_chunks: int) -> tuple[str, set[int] | None]:
    """Separa la marca `FUENTES: N,N,...` que el LLM agrega al final de su respuesta (ver
    SYSTEM_PROMPT) del texto que vera el usuario, y la traduce a los indices 0-based de `chunks`
    que realmente se citaron.

    Devuelve (texto_sin_la_marca, indices_citados). `indices_citados` es un set() vacio si el
    LLM declaro explicitamente que no se baso en ningun fragmento puntual, o None si la marca no
    aparecio o no se pudo parsear (el LLM no siguio el formato) -- en ese caso el llamador debe
    asumir que no hay informacion confiable y mostrar todos los fragmentos recuperados como
    fuentes (comportamiento previo, mas ruidoso pero nunca oculta una cita real).
    """
    match = _SOURCES_FOOTER_RE.search(response_text)
    if not match:
        return response_text, None

    cleaned_text = response_text[: match.start()].rstrip()
    raw = match.group(1).strip().lower()
    if raw in ("", "ninguna", "ninguno", "none"):
        return cleaned_text, set()

    normalized = raw.replace(" y ", ",").replace(";", ",")
    indices: set[int] = set()
    for part in normalized.split(","):
        part = part.strip()
        if part.isdigit():
            n = int(part)
            if 1 <= n <= total_chunks:
                indices.add(n - 1)

    if not indices:
        return cleaned_text, None

    return cleaned_text, indices


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
    score y ubicacion normativa) que el LLM declaro haber citado (ver _extract_cited_sources),
    no todos los recuperados como contexto.

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
        response_text, cited_indices = _extract_cited_sources(response_text, len(relevant_chunks))

        # Si el LLM declaro cuales [Fuente N] cito de verdad, solo esas se muestran como fuentes
        # (ver _extract_cited_sources); si no pudo parsearse (None), se cae al comportamiento
        # previo de mostrar todo lo recuperado, para no ocultar una cita real por un fallo de
        # formato.
        chunks_to_show = (
            [relevant_chunks[i] for i in sorted(cited_indices)] if cited_indices is not None else relevant_chunks
        )

        sources = [
            {
                "document_id": str(chunk["document_id"]),
                "document_name": filenames.get(chunk["document_id"], "desconocido"),
                "chunk_index": chunk["chunk_index"],
                "score": chunk["score"],
                "numero_articulo": chunk["numero_articulo"],
                "pagina_origen": chunk["pagina_origen"],
            }
            for chunk in chunks_to_show
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
