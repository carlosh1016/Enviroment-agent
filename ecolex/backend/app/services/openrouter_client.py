"""Cliente HTTP minimo para la API de chat completions de OpenRouter.

Usado por el pipeline de ingesta (ingestion_service.py) para limpiar texto extraido de PDFs
y para transcribir paginas escaneadas via un modelo multimodal.
"""

import asyncio

import httpx

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)

BASE_URL = "https://openrouter.ai/api/v1"
CHAT_COMPLETIONS_URL = f"{BASE_URL}/chat/completions"

REQUEST_TIMEOUT_SECONDS = 60
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = (2, 4, 8)


class InternalServiceError(Exception):
    """Error irrecuperable al invocar un servicio externo (OpenRouter)."""


async def chat_completion(messages: list[dict], model: str, max_tokens: int) -> str:
    """Llama a POST /chat/completions de OpenRouter y retorna el texto de la respuesta.

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
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens}

    last_error_detail = "sin detalle"

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as http_client:
        for attempt in range(MAX_ATTEMPTS):
            is_last_attempt = attempt == MAX_ATTEMPTS - 1

            try:
                response = await http_client.post(CHAT_COMPLETIONS_URL, headers=headers, json=payload)
            except httpx.HTTPError as exc:
                last_error_detail = f"error de red: {exc}"
                logger.warning(
                    "Fallo de red llamando a OpenRouter (intento %d/%d): %s", attempt + 1, MAX_ATTEMPTS, exc
                )
            else:
                if response.status_code == 200:
                    data = response.json()
                    return data["choices"][0]["message"]["content"]

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
