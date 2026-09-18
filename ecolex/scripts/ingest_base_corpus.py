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

REQUEST_TIMEOUT_SECONDS = 120
POLL_INTERVAL_SECONDS = 3
POLL_MAX_SECONDS = 300

# Rutas en Windows, donde corre este script.
DOCUMENTS = [
    r"/mnt/c/Users/carlos.hernandezc/Downloads/Decreto_1076_de_2015_Sector_Ambiente_y_Desarrollo_Sostenible.pdf",
    r"/mnt/c/Users/carlos.hernandezc/Downloads/Guía_Informativa__Estructura_y_Regulación_del_Sector_Ambiente_y_Desarrollo_Sostenible_Decreto_1076_de_2015.pdf",
    r"/mnt/c/Users/carlos.hernandezc/Downloads/Resolucion-0627-de-2006.pdf",
    r"/mnt/c/Users/carlos.hernandezc/Downloads/resolucion-1541-de-2013.pdf",
    r"/mnt/c/Users/carlos.hernandezc/Downloads/resolucion-909-de-2008.pdf",
    r"/mnt/c/Users/carlos.hernandezc/Downloads/Resolucion-2254-de-2017.pdf",
    r"/mnt/c/Users/carlos.hernandezc/Downloads/resolucion-0316-de-2018.pdf",
    r"/mnt/c/Users/carlos.hernandezc/Downloads/resolucion-631-de-2015.pdf",
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


def poll_document_status(token: str, document_id: str, filename: str) -> dict:
    """Hace polling a GET /documents/{id} cada POLL_INTERVAL_SECONDS hasta que status != 'processing'."""
    deadline = time.monotonic() + POLL_MAX_SECONDS

    while True:
        response = requests.get(
            DOCUMENT_URL_TEMPLATE.format(document_id=document_id),
            headers={"Authorization": f"Bearer {token}"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code == 401:
            raise _Unauthorized()
        if response.status_code != 200:
            raise IngestionError(f"No se pudo consultar el documento {document_id}: {response.text}")

        document = response.json()["data"]
        if document["status"] != "processing":
            return document

        if time.monotonic() >= deadline:
            raise IngestionError(
                f"'{filename}' sigue en 'processing' tras {POLL_MAX_SECONDS}s, se abandona el polling"
            )

        time.sleep(POLL_INTERVAL_SECONDS)


def ingest_one(token_holder: dict, file_path: Path) -> tuple[dict | None, str | None]:
    """Sube y espera un documento. Retorna (documento_final_o_None, mensaje_de_error_o_None).

    Si el token expira (401) en cualquier paso, hace un re-login automatico y reintenta una vez.
    """
    filename = file_path.name

    for attempt in range(2):
        try:
            document_id = upload_document(token_holder["token"], file_path)
            document = poll_document_status(token_holder["token"], document_id, filename)

            if document["status"] == "error":
                return None, document.get("error_message") or "Error desconocido durante el procesamiento"

            return document, None

        except _Unauthorized:
            if attempt == 0:
                logger.warning("Token expirado o invalido, reintentando login...")
                token_holder["token"] = login()
                continue
            return None, "Token expirado y el re-login tambien fallo"

    return None, "No se pudo procesar tras reintentar"


def main() -> int:
    logger.info("Iniciando ingesta del corpus base ambiental (%d documentos)", len(DOCUMENTS))

    token_holder = {"token": login()}

    processed = 0
    total_chunks = 0
    errors: list[tuple[str, str]] = []

    for raw_path in DOCUMENTS:
        file_path = Path(raw_path)

        if not file_path.is_file():
            logger.warning("Archivo no encontrado, se omite: %s", raw_path)
            errors.append((file_path.name, "Archivo no encontrado en disco"))
            continue

        logger.info("Procesando: %s", file_path.name)
        document, error_message = ingest_one(token_holder, file_path)
        processed += 1

        if error_message:
            logger.error("Error procesando '%s': %s", file_path.name, error_message)
            errors.append((file_path.name, error_message))
        else:
            chunk_count = document["chunk_count"]
            total_chunks += chunk_count
            logger.info("'%s' listo: %d chunks generados", file_path.name, chunk_count)

    logger.info("=" * 60)
    logger.info("RESUMEN DE INGESTA")
    logger.info("Documentos procesados: %d/%d", processed, len(DOCUMENTS))
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
