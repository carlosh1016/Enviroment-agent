import asyncio
import io
import uuid

from docx import Document as DocxDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from pypdf import PdfReader
from sqlalchemy.ext.asyncio import AsyncSession

from app import database as app_database
from app.config import settings
from app.logging_config import get_logger
from app.models.document import Document, DocumentChunk, DocumentStatus

logger = get_logger(__name__)

EMBEDDING_MODEL = "models/gemini-embedding-001"
EMBEDDING_DIMENSIONS = 768
EMBEDDING_BATCH_SIZE = 20
EMBEDDING_BATCH_TIMEOUT_SECONDS = 60


def parse_document(file_bytes: bytes, file_type: str) -> str:
    """Extrae el texto plano de un archivo PDF, DOCX o TXT. Lanza ValueError si queda vacio o ilegible."""
    if file_type == "pdf":
        text = _parse_pdf(file_bytes)
    elif file_type == "docx":
        text = _parse_docx(file_bytes)
    elif file_type == "txt":
        text = file_bytes.decode("utf-8", errors="replace")
    else:
        raise ValueError(f"Tipo de archivo no soportado: {file_type}")

    if len(text.strip()) < 50:
        raise ValueError("Documento vacio o ilegible")

    return text


def _parse_pdf(file_bytes: bytes) -> str:
    """Extrae texto de un PDF pagina por pagina y lo une con doble salto de linea."""
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages)


def _parse_docx(file_bytes: bytes) -> str:
    """Extrae texto de un DOCX, incluyendo parrafos y celdas de tablas."""
    doc = DocxDocument(io.BytesIO(file_bytes))
    parts = [paragraph.text for paragraph in doc.paragraphs if paragraph.text]

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text:
                    parts.append(cell.text)

    return "\n\n".join(parts)


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> list[str]:
    """Divide el texto en fragmentos superpuestos, descartando los menores a 50 caracteres."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", ". ", " "],
    )
    raw_chunks = splitter.split_text(text)
    return [chunk for chunk in raw_chunks if len(chunk) >= 50]


async def embed_chunks(chunks: list[str]) -> list[list[float]]:
    """Genera embeddings de dimension 768 para una lista de chunks, en batches de 20 para no exceder rate limits."""
    embedder = GoogleGenerativeAIEmbeddings(
        model=EMBEDDING_MODEL,
        google_api_key=settings.GOOGLE_API_KEY,
        output_dimensionality=EMBEDDING_DIMENSIONS,
    )

    vectors: list[list[float]] = []
    for i in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
        batch = chunks[i : i + EMBEDDING_BATCH_SIZE]
        try:
            batch_vectors = await asyncio.wait_for(
                embedder.aembed_documents(batch), timeout=EMBEDDING_BATCH_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError as exc:
            raise TimeoutError(
                f"Timeout generando embeddings: el batch {i // EMBEDDING_BATCH_SIZE} "
                f"no respondio en {EMBEDDING_BATCH_TIMEOUT_SECONDS}s"
            ) from exc
        vectors.extend(batch_vectors)
        await asyncio.sleep(2)

    return vectors


async def process_document(
    db: AsyncSession,
    document_id: uuid.UUID,
    file_bytes: bytes,
    file_type: str,
    tenant_id: uuid.UUID,
) -> None:
    """Orquesta el pipeline de ingesta: parseo, chunking, embeddings e insercion de chunks en bulk.

    Si cualquier paso falla, deja el documento en status='error' con el detalle en error_message.
    """
    document = await db.get(Document, document_id)
    if document is None:
        logger.error("Documento no encontrado al iniciar el procesamiento")
        return

    document.status = DocumentStatus.PROCESSING
    await db.commit()

    try:
        text = await asyncio.to_thread(parse_document, file_bytes, file_type)
        chunks = await asyncio.to_thread(chunk_text, text)
        if not chunks:
            raise ValueError("No se pudieron generar fragmentos del documento")

        vectors = await embed_chunks(chunks)

        for index, (chunk_content, vector) in enumerate(zip(chunks, vectors)):
            db.add(
                DocumentChunk(
                    tenant_id=tenant_id,
                    document_id=document_id,
                    chunk_index=index,
                    content=chunk_content,
                    embedding=vector,
                )
            )

        document.status = DocumentStatus.READY
        document.chunk_count = len(chunks)
        document.error_message = None
        await db.commit()

        logger.info("Documento procesado exitosamente")
    except Exception as exc:
        await db.rollback()
        document = await db.get(Document, document_id)
        if document is not None:
            document.status = DocumentStatus.ERROR
            document.error_message = str(exc)[:1000]
            await db.commit()
        logger.error("Error procesando documento: %s", type(exc).__name__)


async def process_document_background(
    document_id: uuid.UUID,
    file_bytes: bytes,
    file_type: str,
    tenant_id: uuid.UUID,
) -> None:
    """Wrapper para ejecutar process_document como BackgroundTask, con su propia sesion de base de datos.

    Referencia app_database.AsyncSessionLocal por atributo de modulo (no por import directo) para que
    los tests puedan sustituirlo por su propio session factory de SQLite en memoria.
    """
    async with app_database.AsyncSessionLocal() as db:
        await process_document(db, document_id, file_bytes, file_type, tenant_id)
