"""Sincronizador automatico del corpus normativo compartido (tenant _base) contra el listado
publico de normativa de Minambiente (https://www.minambiente.gov.co/normativa/).

Alcance deliberado de la v1 (ver CLAUDE.md "Sincronizacion automatica de normativa"):
- Solo Minambiente (no Funcion Publica: ese sitio es una app legada mucho menos estructurada,
  y ademas Croma -- que indexa esa misma fuente -- demostro tener cobertura ambiental muy
  delgada ahi, ver auditoria de API externa de 2026-10-21).
- Solo agrega normas NUEVAS (nunca reemplaza ni borra una ya ingestada). Deteccion de posible
  derogacion/modificacion es una ADVERTENCIA simple basada en palabras clave del titulo
  (ver detect_supersession), nunca un reemplazo automatico de contenido.
- Solo revisa la pagina 1 de cada categoria: las entradas vienen en orden descendente de
  publicacion, asi que cualquier norma nueva siempre aparece ahi. Paginas mas profundas solo
  servirian para una carga historica inicial (fuera de alcance de la sincronizacion diaria).
"""

import asyncio
import hashlib
import re
import urllib.parse
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import database as app_database
from app.logging_config import get_logger
from app.models.document import Document, DocumentFileType, DocumentStatus
from app.models.external_norm import ExternalNorm, ExternalNormSource, ExternalNormStatus
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.services import ingestion_service
from app.services.rag_service import BASE_TENANT_SLUG

logger = get_logger(__name__)

BASE_URL = "https://www.minambiente.gov.co"
DEFAULT_CATEGORIES = ["resoluciones", "decretos", "circulares", "conpes"]

# Mismo esquema que app/routers/documents.py:_storage_path (duplicado adrede: ese modulo
# depende de ingestion_service, no al reves, para evitar un import circular).
STORAGE_DIR = Path("storage/documents")

# Solo se ingestan PDFs: la pagina tambien enlaza ocasionalmente .zip/.docx (ver hallazgo del
# 2026-10-21, una Resolucion publicada como .zip), que el pipeline de ingesta no soporta.
PDF_EXTENSION = ".pdf"

MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

# Palabras clave que, en el titulo de una norma NUEVA, sugieren que afecta la vigencia de una
# norma YA publicada (no necesariamente ya ingestada en nuestro corpus). Deliberadamente amplio
# (preferible un falso positivo marcado para revision manual, a silenciosamente dejar pasar una
# derogacion real).
SUPERSESSION_KEYWORDS = [
    "deroga", "derogatoria", "modifica", "sustituye", "subroga",
    "revoca", "revocatoria", "aclara", "aclaratoria", "corrige", "correccion", "corrección",
]

# Captura el numero de una norma mencionada en el titulo (ej. "Resolucion 956", "Res. 956",
# "Decreto 393"), para distinguir el numero propio de la norma del numero de la norma referida.
NORM_REFERENCE_RE = re.compile(
    r"(?:resoluci[oó]n|res\.?|decreto|circular)\s*(?:no\.?)?\s*(\d+)", re.IGNORECASE
)

# Identifica una norma por (tipo, numero, anio) a partir de un titulo O un nombre de archivo (ej.
# "Decreto 1076 de 2015" y "Decreto_1076_de_2015_Sector_Ambiente....pdf" deben dar el mismo
# resultado) -- ver _extract_norm_identity. [\s_-]* en vez de \s* porque los nombres de archivo
# reales usan guiones/guiones bajos donde el titulo en pantalla usa espacios.
NORM_IDENTITY_RE = re.compile(
    r"(resoluci[oó]n|decreto|circular|conpes)s?\.?[\s_-]*(?:no\.?)?[\s_-]*0*(\d+)\D{0,20}?(\d{4})",
    re.IGNORECASE,
)


def _extract_norm_identity(text: str) -> tuple[str, int, int] | None:
    """Extrae (tipo, numero, anio) de un titulo o nombre de archivo (ej. 'Decreto 1076 de 2015'
    o 'Resolucion-909-de-2008.pdf' -> ('decreto', 1076, 2015) / ('resolucion', 909, 2008)). None
    si no se reconoce el patron.

    Se usa para detectar cuando una norma que el scraper encuentra en Minambiente YA esta en el
    corpus base bajo un pdf_url distinto (ver _load_base_corpus_identities): el dedupe normal es
    por pdf_url EXACTO, que no sirve aqui porque el documento original pudo haberse cargado a
    mano desde un archivo distinto al que hoy sirve Minambiente (visto en vivo el 2026-10-26:
    "Decreto 1076 de 2015" ya estaba en el corpus desde la carga manual inicial, pero el scraper
    lo iba a re-ingestar como si fuera nuevo porque su pdf_url en Minambiente nunca se habia
    visto)."""
    match = NORM_IDENTITY_RE.search(text)
    if not match:
        return None
    tipo, numero, anio = match.groups()
    return (tipo.lower().replace("ó", "o"), int(numero), int(anio))


async def _load_base_corpus_identities(
    db: AsyncSession, base_tenant_id: uuid.UUID
) -> dict[tuple[str, int, int], uuid.UUID]:
    """Carga, UNA SOLA VEZ por corrida (ver sync_all), un mapa {(tipo, numero, anio):
    document_id} de los documentos ya existentes en el corpus base, para que
    _get_or_create_external_norm pueda saltarse la ingesta de una norma que Minambiente lista
    pero que ya esta en el corpus bajo un pdf_url distinto."""
    result = await db.execute(select(Document.id, Document.filename).where(Document.tenant_id == base_tenant_id))
    identities: dict[tuple[str, int, int], uuid.UUID] = {}
    for document_id, filename in result.all():
        identity = _extract_norm_identity(filename)
        if identity is not None and identity not in identities:
            identities[identity] = document_id
    return identities


@dataclass
class SyncStats:
    category: str
    seen: int = 0
    new: int = 0
    ingested: int = 0
    failed: int = 0
    skipped_non_pdf: int = 0
    supersession_warnings: int = 0
    errors: list[str] = field(default_factory=list)


def _parse_published_at(raw_text: str | None) -> date | None:
    """Convierte 'Publicado: septiembre 8, 2026' en date(2026, 9, 8). None si no se puede parsear."""
    if not raw_text:
        return None
    match = re.search(r"([a-záéíóú]+)\s+(\d{1,2}),?\s+(\d{4})", raw_text.strip().lower())
    if not match:
        return None
    mes_nombre, dia, anio = match.groups()
    mes = MESES_ES.get(mes_nombre)
    if mes is None:
        return None
    try:
        return date(int(anio), mes, int(dia))
    except ValueError:
        return None


def _filename_as_text(pdf_url: str) -> str:
    """Convierte el nombre de archivo de una URL en texto buscable: a menudo la pista de que una
    norma deroga/aclara/modifica otra esta SOLO en el nombre del PDF, no en el titulo mostrado en
    la pagina (ej. 'Resolucion-1067-del-19-AGO-2026-ACLARA-la-Res.-956-2026_.pdf' se muestra en
    pantalla solo como 'Resolución 1067 de 2026')."""
    filename = urllib.parse.unquote(pdf_url.rsplit("/", 1)[-1])
    filename = re.sub(r"\.[a-zA-Z0-9]{2,5}$", "", filename)
    return re.sub(r"[-_.]+", " ", filename)


def detect_supersession(title: str, pdf_url: str | None = None) -> str | None:
    """Si el titulo o el nombre del PDF sugieren que esta norma deroga/modifica/aclara/revoca
    otra, devuelve una nota de advertencia para revision manual (nunca reemplaza contenido
    automaticamente)."""
    filename_text = _filename_as_text(pdf_url) if pdf_url else ""
    combined = f"{title} {filename_text}"
    lowered = combined.lower()
    if not any(keyword in lowered for keyword in SUPERSESSION_KEYWORDS):
        return None

    own_numbers = NORM_REFERENCE_RE.findall(title)
    own_number = own_numbers[0] if own_numbers else None
    all_numbers = NORM_REFERENCE_RE.findall(combined)
    referenced = [n for n in all_numbers if n != own_number]

    if referenced:
        return (
            f"El titulo o nombre de archivo sugiere que esta norma afecta la vigencia de otra "
            f"(posible numero referido: {', '.join(sorted(set(referenced)))}). "
            f"Titulo: '{title}'. Archivo: '{filename_text.strip()}'. "
            f"Revisar manualmente si alguna norma ya cargada en el corpus base queda "
            f"desactualizada."
        )
    return (
        f"El titulo o nombre de archivo sugiere que esta norma afecta la vigencia de otra, pero "
        f"no se pudo identificar el numero referido. Titulo: '{title}'. "
        f"Archivo: '{filename_text.strip()}'. Revisar manualmente."
    )


async def fetch_category_entries(client: httpx.AsyncClient, category: str, page: int = 1) -> list[dict]:
    """Descarga y parsea la pagina `page` del listado de `category` (ej. 'resoluciones').
    Devuelve una lista de dicts: {title, pdf_url, published_at}."""
    url = f"{BASE_URL}/normativa/{category}/"
    if page > 1:
        url = f"{url}page/{page}/"

    response = await client.get(url, timeout=30.0)
    if response.status_code == 404:
        return []
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    entries = []
    for row in soup.select("div.row.box-docgd"):
        link = row.select_one("a.documento-normativa")
        if link is None or not link.get("href"):
            continue
        title = (link.get("title") or link.text or "").strip()
        if not title:
            continue
        # Dos spans comparten la clase "txt-peque-archivo" en cada fila (uno vacio, para el
        # tamano del archivo, y otro con "Publicado: ..."): hay que elegir el que tiene texto.
        date_span = next(
            (s for s in row.select("span.txt-peque-archivo") if "Publicado" in s.text), None
        )
        published_at = _parse_published_at(date_span.text if date_span else None)
        entries.append({"title": title, "pdf_url": link["href"].strip(), "published_at": published_at})

    return entries


async def _get_or_create_external_norm(
    db: AsyncSession,
    category: str,
    entry: dict,
    existing_identities: dict[tuple[str, int, int], uuid.UUID],
) -> tuple[ExternalNorm, bool]:
    """Devuelve (fila, es_candidata_a_ingestar). Si ya existe una fila con ese pdf_url:
    - status ingested: se deja tal cual, no es candidata (ya se procesa).
    - status failed O pending: SI es candidata -- failed puede ser un error transitorio (ej. el
      402 de OpenRouter por presupuesto de requests en vuelo, ver openrouter_client.py), y
      pending SOLO puede quedar asi si el proceso se interrumpio a medio commit (ej. el proceso
      matado por falta de memoria del sistema, visto en vivo el 2026-10-26: dentro de una
      corrida, cada entrada se procesa y comitea antes de pasar a la siguiente, nunca queda
      "pending en reposo" en operacion normal). Ninguno de los dos debe quedar bloqueado para
      siempre solo porque el dedupe es por pdf_url. Se limpia el Document roto de la corrida
      anterior (si quedo alguno) y se deja la fila en PENDING para reintentar ahora.

    Si NO existe una fila para este pdf_url pero `existing_identities` (ver
    _load_base_corpus_identities) indica que esta misma norma (mismo tipo+numero+anio) ya esta
    en el corpus base bajo un pdf_url distinto (ej. cargada a mano), se crea la fila ya como
    INGESTED enlazada a ese documento existente, SIN descargar ni gastar nada en ingestarla de
    nuevo -- no es candidata.
    """
    result = await db.execute(select(ExternalNorm).where(ExternalNorm.pdf_url == entry["pdf_url"]))
    existing = result.scalar_one_or_none()
    if existing is not None:
        if existing.status == ExternalNormStatus.INGESTED:
            return existing, False

        if existing.document_id is not None:
            stale_document_id = existing.document_id
            await db.execute(delete(Document).where(Document.id == stale_document_id))
            stale_path = STORAGE_DIR / f"{stale_document_id}.pdf"
            await asyncio.to_thread(stale_path.unlink, missing_ok=True)
            existing.document_id = None

        existing.status = ExternalNormStatus.PENDING
        existing.error_message = None
        return existing, True

    identity = _extract_norm_identity(entry["title"])
    duplicate_document_id = existing_identities.get(identity) if identity is not None else None
    if duplicate_document_id is not None:
        logger.info(
            "Norma '%s' ya existe en el corpus base (document_id=%s); no se re-ingesta",
            entry["title"],
            duplicate_document_id,
        )

    norm = ExternalNorm(
        source=ExternalNormSource.MINAMBIENTE,
        category=category,
        title=entry["title"],
        pdf_url=entry["pdf_url"],
        published_at=entry["published_at"],
        status=ExternalNormStatus.INGESTED if duplicate_document_id else ExternalNormStatus.PENDING,
        document_id=duplicate_document_id,
        supersedes_note=detect_supersession(entry["title"], entry["pdf_url"]),
    )
    db.add(norm)
    await db.flush()
    return norm, duplicate_document_id is None


async def sync_category(
    db: AsyncSession,
    client: httpx.AsyncClient,
    category: str,
    base_tenant_id: uuid.UUID,
    base_admin_user_id: uuid.UUID | None,
    existing_identities: dict[tuple[str, int, int], uuid.UUID],
    max_new: int | None = None,
) -> SyncStats:
    """Sincroniza una sola categoria (ej. 'resoluciones'): descubre entradas nuevas, las registra
    en external_norms y dispara la ingesta real (misma logica que una subida manual de admin).

    `max_new`: tope de normas NUEVAS a ingestar en esta corrida (None = sin tope). Pensado para
    la primera corrida real contra una fuente nunca sincronizada antes, donde TODA la pagina 1
    cuenta como "nueva" (puede ser un centenar de PDFs) -- en el estado estable del dia a dia,
    tipicamente hay 0-2 nuevas por categoria y el tope no se alcanza nunca.

    `existing_identities`: ver _load_base_corpus_identities (cargado una vez por sync_all, no por
    categoria, porque el corpus base no cambia dentro de una misma corrida)."""
    stats = SyncStats(category=category)

    try:
        entries = await fetch_category_entries(client, category)
    except httpx.HTTPError as exc:
        stats.errors.append(f"No se pudo descargar el listado de {category}: {exc}")
        return stats

    stats.seen = len(entries)

    for entry in entries:
        if max_new is not None and stats.new >= max_new:
            break

        if not entry["pdf_url"].lower().endswith(PDF_EXTENSION):
            stats.skipped_non_pdf += 1
            continue

        norm, is_new = await _get_or_create_external_norm(db, category, entry, existing_identities)
        if not is_new:
            # Cubre tanto el caso de no-op (fila ya INGESTED de antes) como el caso real: una
            # fila NUEVA creada recien, ya enlazada a un duplicado del corpus base (ver
            # _get_or_create_external_norm) -- sin este commit, si el resto de la corrida no
            # vuelve a tocar ninguna candidata real, ese insert se perderia al cerrar la sesion
            # sin commit.
            await db.commit()
            continue

        stats.new += 1
        if norm.supersedes_note:
            stats.supersession_warnings += 1
            logger.warning("Posible derogacion/modificacion detectada: %s", norm.title)

        try:
            pdf_response = await client.get(entry["pdf_url"], timeout=60.0)
            pdf_response.raise_for_status()
            file_bytes = pdf_response.content
            norm.content_hash = hashlib.sha256(file_bytes).hexdigest()

            document = Document(
                tenant_id=base_tenant_id,
                uploaded_by=base_admin_user_id,
                filename=entry["pdf_url"].rsplit("/", 1)[-1],
                file_type=DocumentFileType.PDF,
                file_size_bytes=len(file_bytes),
                status=DocumentStatus.PROCESSING,
                is_base_corpus=True,
            )
            db.add(document)
            await db.flush()

            storage_path = STORAGE_DIR / f"{document.id}.pdf"
            await asyncio.to_thread(storage_path.parent.mkdir, parents=True, exist_ok=True)
            await asyncio.to_thread(storage_path.write_bytes, file_bytes)

            await ingestion_service.process_document(db, document.id, file_bytes, "pdf", base_tenant_id)
            await db.refresh(document)

            norm.document_id = document.id
            norm.status = (
                ExternalNormStatus.INGESTED if document.status == DocumentStatus.READY else ExternalNormStatus.FAILED
            )
            if document.status != DocumentStatus.READY:
                norm.error_message = document.error_message
                stats.failed += 1
            else:
                stats.ingested += 1
        except httpx.HTTPError as exc:
            norm.status = ExternalNormStatus.FAILED
            norm.error_message = f"Error descargando el PDF: {exc}"
            stats.failed += 1
            stats.errors.append(f"{entry['title']}: {exc}")

        await db.commit()

    return stats


async def sync_all(
    db: AsyncSession,
    base_tenant_id: uuid.UUID,
    base_admin_user_id: uuid.UUID | None,
    categories: list[str] | None = None,
    max_new_per_category: int | None = None,
) -> list[SyncStats]:
    """Punto de entrada principal: sincroniza todas las categorias configuradas."""
    categories = categories or DEFAULT_CATEGORIES
    results = []
    # Una sola vez para toda la corrida (el corpus base no cambia entre categorias): ver
    # _load_base_corpus_identities y el bug real que evita (Decreto 1076 de 2015 re-ingestado
    # como duplicado el 2026-10-26 porque ya estaba en el corpus, cargado a mano, bajo un
    # pdf_url distinto al que lista Minambiente).
    existing_identities = await _load_base_corpus_identities(db, base_tenant_id)
    async with httpx.AsyncClient(
        headers={"User-Agent": "EcolexCorpusSync/0.1 (+https://github.com/; uso interno, revisa la normativa publica)"}
    ) as client:
        for category in categories:
            stats = await sync_category(
                db,
                client,
                category,
                base_tenant_id,
                base_admin_user_id,
                existing_identities,
                max_new=max_new_per_category,
            )
            results.append(stats)
    return results


async def run_sync_job(max_new_per_category: int | None = None) -> list[SyncStats]:
    """Punto de entrada de alto nivel: abre su propia sesion de DB, resuelve el tenant/admin
    _base y corre sync_all. Usado tanto por el script manual (app/scripts/sync_minambiente_corpus.py)
    como por el scheduler opcional (ver app/main.py, ENABLE_NORM_SYNC_SCHEDULER)."""
    async with app_database.AsyncSessionLocal() as db:
        tenant_result = await db.execute(select(Tenant).where(Tenant.slug == BASE_TENANT_SLUG))
        base_tenant = tenant_result.scalar_one_or_none()
        if base_tenant is None:
            logger.error("No existe el tenant _base: no se puede sincronizar normativa")
            return []

        admin_result = await db.execute(
            select(User).where(User.tenant_id == base_tenant.id, User.role == UserRole.ADMIN).limit(1)
        )
        base_admin = admin_result.scalar_one_or_none()

        logger.info("Iniciando sincronizacion de normativa de Minambiente")
        all_stats = await sync_all(
            db,
            base_tenant_id=base_tenant.id,
            base_admin_user_id=base_admin.id if base_admin else None,
            max_new_per_category=max_new_per_category,
        )

        for stats in all_stats:
            logger.info(
                "Categoria %s: vistas=%d nuevas=%d ingestadas=%d fallidas=%d "
                "omitidas_no_pdf=%d advertencias_derogacion=%d",
                stats.category,
                stats.seen,
                stats.new,
                stats.ingested,
                stats.failed,
                stats.skipped_non_pdf,
                stats.supersession_warnings,
            )
            for error in stats.errors:
                logger.warning("Error en %s: %s", stats.category, error)

        logger.info(
            "Sincronizacion completa: %d normas nuevas, %d ingestadas, %d fallidas, %d advertencias",
            sum(s.new for s in all_stats),
            sum(s.ingested for s in all_stats),
            sum(s.failed for s in all_stats),
            sum(s.supersession_warnings for s in all_stats),
        )
        return all_stats
