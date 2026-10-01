"""Cliente HTTP minimo para la API de OpenRouter (chat completions y embeddings).

Usado por el pipeline de ingesta (ingestion_service.py) para limpiar texto extraido de PDFs,
transcribir paginas escaneadas y generar embeddings, y por rag_service.py para responder y
embeber las consultas.
"""

import asyncio

import httpx

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)

BASE_URL = "https://openrouter.ai/api/v1"
CHAT_COMPLETIONS_URL = f"{BASE_URL}/chat/completions"
EMBEDDINGS_URL = f"{BASE_URL}/embeddings"

REQUEST_TIMEOUT_SECONDS = 60
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = (2, 4, 8)


class InternalServiceError(Exception):
    """Error irrecuperable al invocar un servicio externo (OpenRouter)."""


async def _post_with_retry(url: str, payload: dict) -> dict:
    """POST JSON a OpenRouter y retorna el body ya parseado.

    Reintenta hasta MAX_ATTEMPTS veces con backoff exponencial ante errores transitorios
    (429, 5xx o fallas de red). Un error 4xx distinto a 429 (ej. 401 por API key invalida)
    se considera irrecuperable y no se reintenta.
    """
    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "HTTP-Referer": "http://localhost",
        "X-Title": "ecolex",
        "Content-Type": "application/json",
    }

    last_error_detail = "sin detalle"

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as http_client:
        for attempt in range(MAX_ATTEMPTS):
            is_last_attempt = attempt == MAX_ATTEMPTS - 1

            try:
                response = await http_client.post(url, headers=headers, json=payload)
            except httpx.HTTPError as exc:
                last_error_detail = f"error de red: {exc}"
                logger.warning(
                    "Fallo de red llamando a OpenRouter (intento %d/%d): %s", attempt + 1, MAX_ATTEMPTS, exc
                )
            else:
                if response.status_code == 200:
                    return response.json()

                last_error_detail = f"HTTP {response.status_code}: {response.text[:500]}"

                if response.status_code != 429 and response.status_code < 500:
                    raise InternalServiceError(f"OpenRouter respondio {last_error_detail}")

                logger.warning(
                    "OpenRouter respondio %d (intento %d/%d), reintentando",
                    response.status_code,
                    attempt + 1,
                    MAX_ATTEMPTS,
                )

            if not is_last_attempt:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS[attempt])

    raise InternalServiceError(f"OpenRouter fallo tras {MAX_ATTEMPTS} intentos ({last_error_detail})")


async def chat_completion(messages: list[dict], model: str, max_tokens: int) -> str:
    """Llama a POST /chat/completions de OpenRouter y retorna el texto de la respuesta."""
    data = await _post_with_retry(
        CHAT_COMPLETIONS_URL, {"model": model, "messages": messages, "max_tokens": max_tokens}
    )
    return data["choices"][0]["message"]["content"]


async def create_embeddings(texts: list[str], model: str, dimensions: int) -> list[list[float]]:
    """Llama a POST /embeddings de OpenRouter y retorna un vector por texto, en el mismo orden.

    `dimensions` recorta el vector al tamano de la columna pgvector (solo modelos entrenados
    para ello, como qwen3-embedding, lo hacen sin perder calidad).
    """
    data = await _post_with_retry(EMBEDDINGS_URL, {"model": model, "input": texts, "dimensions": dimensions})
    items = sorted(data["data"], key=lambda item: item["index"])
    if len(items) != len(texts):
        raise InternalServiceError(f"OpenRouter devolvio {len(items)} embeddings para {len(texts)} textos")
    return [item["embedding"] for item in items]
