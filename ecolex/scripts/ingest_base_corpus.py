"""Script operacional de una sola vez: ingesta el corpus normativo ambiental colombiano
en el tenant compartido _base, via los endpoints HTTP de la Fase 2 (no accede a la DB
directamente).

Uso:
    set BASE_ADMIN_EMAIL=admin@base.ecolex.internal
    set BASE_ADMIN_PASSWORD=tu_password
    python scripts/ingest_base_corpus.py

Ver scripts/README_scripts.md para el detalle completo de pre-requisitos.
"""

import logging
import os
import sys
import time
from pathlib import Path

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ingest_base_corpus")

BASE_URL = os.environ.get("BACKEND_BASE_URL", "http://localhost:8000")
LOGIN_URL = f"{BASE_URL}/auth/login"
UPLOAD_URL = f"{BASE_URL}/api/v1/documents/upload"
DOCUMENT_URL_TEMPLATE = f"{BASE_URL}/api/v1/documents/{{document_id}}"

BASE_ADMIN_EMAIL = os.environ.get("BASE_ADMIN_EMAIL")
BASE_ADMIN_PASSWORD = os.environ.get("BASE_ADMIN_PASSWORD")
BASE_TENANT_SLUG = "_base"

REQUEST_TIMEOUT_SECONDS = 300
POLL_INTERVAL_SECONDS = 10
POLL_MAX_SECONDS = 1800

# Rutas en la unidad D: (Descargas), donde corre este script.
DOCUMENTS = [
    r"/mnt/d/Descargas/Decreto_1076_de_2015_Sector_Ambiente_y_Desarrollo_Sostenible.pdf",
    r"/mnt/d/Descargas/Guía Informativa_ Estructura y Regulación del Sector Ambiente y Desarrollo Sostenible (Decreto 1076 de 2015).pdf",
    r"/mnt/d/Descargas/Resolucion-0627-de-2006.pdf",
    r"/mnt/d/Descargas/resolucion-1541-de-2013.pdf",
    r"/mnt/d/Descargas/resolucion-909-de-2008.pdf",
    r"/mnt/d/Descargas/Resolucion-2254-de-2017.pdf",
    r"/mnt/d/Descargas/resolucion-0316-de-2018.pdf",
    r"/mnt/d/Descargas/resolucion-631-de-2015.pdf",
]


class IngestionError(Exception):
    """Error irrecuperable durante la ingesta (ej. credenciales invalidas, backend inalcanzable)."""


class _Unauthorized(Exception):
    """Senal interna: una request recibio 401, hay que re-loguear y reintentar."""


def login() -> str:
    """Inicia sesion como admin del tenant _base y retorna el access token."""
    if not BASE_ADMIN_EMAIL or not BASE_ADMIN_PASSWORD:
        raise IngestionError(
            "Debes definir BASE_ADMIN_EMAIL y BASE_ADMIN_PASSWORD como variables de entorno."
        )

    response = requests.post(
        LOGIN_URL,
        json={"email": BASE_ADMIN_EMAIL, "password": BASE_ADMIN_PASSWORD, "tenant_slug": BASE_TENANT_SLUG},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if response.status_code != 200:
        raise IngestionError(f"Login fallido ({response.status_code}): {response.text}")

    token = response.json()["data"]["access_token"]
    logger.info("Login exitoso como %s", BASE_ADMIN_EMAIL)
    return token


def upload_document(token: str, file_path: Path) -> str:
    """Sube un documento marcado como corpus base (es_base_corpus=true). Retorna el document_id."""
    with file_path.open("rb") as f:
        response = requests.post(
            UPLOAD_URL,
            headers={"Authorization": f"Bearer {token}"},
            files={"file": (file_path.name, f, "application/pdf")},
            data={"es_base_corpus": "true"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

    if response.status_code == 401:
        raise _Unauthorized()
    if response.status_code != 202:
        raise IngestionError(f"Upload fallido ({response.status_code}): {response.text}")

    document = response.json()["data"]
    logger.info("Documento '%s' recibido (id=%s), procesando...", file_path.name, document["id"])
    return document["id"]


def upload_all(token_holder: dict, raw_paths: list[str]) -> tuple[list[dict], list[tuple[str, str]]]:
    """Fase 1: sube todos los documentos sin esperar a que terminen de procesarse.

    Retorna (pendientes, errores). pendientes es una lista de {"document_id", "filename"}
    para cada upload exitoso. Si el token expira (401), hace un re-login automatico y
    reintenta una vez esa misma subida.
    """
    pending: list[dict] = []
    errors: list[tuple[str, str]] = []

    for raw_path in raw_paths:
        file_path = Path(raw_path)

        if not file_path.is_file():
            logger.warning("Archivo no encontrado, se omite: %s", raw_path)
            errors.append((file_path.name, "Archivo no encontrado en disco"))
            continue

        for attempt in range(2):
            try:
                document_id = upload_document(token_holder["token"], file_path)
                logger.info("Subido: %s (id=%s)", file_path.name, document_id)
                pending.append({"document_id": document_id, "filename": file_path.name})
                break
            except _Unauthorized:
                if attempt == 0:
                    logger.warning("Token expirado o invalido, reintentando login...")
                    token_holder["token"] = login()
                    continue
                errors.append((file_path.name, "Token expirado y el re-login tambien fallo"))
            except IngestionError as exc:
                errors.append((file_path.name, str(exc)))
                break

    return pending, errors


def poll_all(token_holder: dict, pending: list[dict]) -> tuple[list[dict], list[tuple[str, str]]]:
    """Fase 2: hace polling cada POLL_INTERVAL_SECONDS sobre todos los documentos pendientes,
    hasta que cada uno termine (ready o error) o se agote POLL_MAX_SECONDS en total.

    Retorna (documentos_listos, errores).
    """
    ready: list[dict] = []
    errors: list[tuple[str, str]] = []
    remaining = list(pending)
    deadline = time.monotonic() + POLL_MAX_SECONDS

    while remaining:
        if time.monotonic() >= deadline:
            for item in remaining:
                errors.append(
                    (item["filename"], f"Sigue en 'processing' tras {POLL_MAX_SECONDS}s, se abandona el polling")
                )
            remaining = []
            break

        still_pending: list[dict] = []
        for item in remaining:
            document_id = item["document_id"]
            filename = item["filename"]

            try:
                response = requests.get(
                    DOCUMENT_URL_TEMPLATE.format(document_id=document_id),
                    headers={"Authorization": f"Bearer {token_holder['token']}"},
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
            except requests.exceptions.RequestException as exc:
                logger.warning("No se pudo consultar '%s' (%s), se reintenta en el siguiente ciclo", filename, exc)
                still_pending.append(item)
                continue

            if response.status_code == 401:
                logger.warning("Token expirado o invalido, reintentando login...")
                token_holder["token"] = login()
                still_pending.append(item)
                continue
            if response.status_code != 200:
                errors.append((filename, f"No se pudo consultar el documento {document_id}: {response.text}"))
                continue

            document = response.json()["data"]
            status = document["status"]

            if status == "ready":
                logger.info("Listo: %s (chunks=%d)", filename, document["chunk_count"])
                ready.append(document)
            elif status == "error":
                message = document.get("error_message") or "Error desconocido durante el procesamiento"
                logger.error("Error: %s — %s", filename, message)
                errors.append((filename, message))
            else:
                still_pending.append(item)

        remaining = still_pending
        if remaining:
            time.sleep(POLL_INTERVAL_SECONDS)

    return ready, errors


def main() -> int:
    logger.info("Iniciando ingesta del corpus base ambiental (%d documentos)", len(DOCUMENTS))

    token_holder = {"token": login()}

    logger.info("Fase 1: subiendo %d documentos", len(DOCUMENTS))
    pending, upload_errors = upload_all(token_holder, DOCUMENTS)

    logger.info("Fase 2: esperando a que %d documentos terminen de procesarse", len(pending))
    ready, poll_errors = poll_all(token_holder, pending)

    errors = upload_errors + poll_errors
    total_chunks = sum(document["chunk_count"] for document in ready)

    logger.info("=" * 60)
    logger.info("RESUMEN DE INGESTA")
    logger.info("Documentos procesados: %d/%d", len(ready) + len(errors), len(DOCUMENTS))
    logger.info("Total de chunks generados: %d", total_chunks)
    if errors:
        logger.info("Documentos con error (%d):", len(errors))
        for filename, message in errors:
            logger.info("  - %s: %s", filename, message)
    else:
        logger.info("Sin errores.")
    logger.info("=" * 60)

    return 1 if errors else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except IngestionError as exc:
        logger.error("Ingesta abortada: %s", exc)
        sys.exit(1)
