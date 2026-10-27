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

# El 402 "in_flight_budget_exhausted" de OpenRouter (ver _is_in_flight_budget_error) es
# transitorio: significa que el presupuesto de requests EN VUELO de esta API key (una fraccion
# del limite configurado en la key, no del saldo real disponible) esta temporalmente agotado, y
# se resuelve solo cuando esas requests "se asientan" -- OpenRouter manda un header Retry-After
# (tipicamente 120s) pidiendo esperar. Se maneja aparte de MAX_ATTEMPTS/RETRY_BACKOFF_SECONDS
# (esos son para fallas de red/429/5xx, con esperas cortas de segundos) porque aqui las esperas
# son largas y, en una ingesta secuencial de muchos documentos, un solo tropiezo no deberia
# marcar el documento como fallido para siempre (ver minambiente_sync_service.py).
IN_FLIGHT_BUDGET_MAX_ATTEMPTS = 4
IN_FLIGHT_BUDGET_DEFAULT_WAIT_SECONDS = 120.0


class InternalServiceError(Exception):
    """Error irrecuperable al invocar un servicio externo (OpenRouter)."""


def _is_in_flight_budget_error(response: httpx.Response) -> bool:
    """True si la respuesta es el 402 especifico de OpenRouter por presupuesto de requests en
    vuelo agotado (ver comentario de IN_FLIGHT_BUDGET_MAX_ATTEMPTS). Un 402 por otro motivo (ej.
    saldo real insuficiente) NO es transitorio y no debe reintentarse."""
    if response.status_code != 402:
        return False
    try:
        body = response.json()
    except ValueError:
        return False
    reason = (body.get("error") or {}).get("metadata", {}).get("reason")
    return reason == "in_flight_budget_exhausted"


def _retry_after_seconds(response: httpx.Response, default: float) -> float:
    """Lee el header Retry-After (segundos) de la respuesta; `default` si falta o no es numerico."""
    raw = response.headers.get("Retry-After")
    if raw is None:
        return default
    try:
        return max(float(raw), 0.0)
    except ValueError:
        return default


async def _post_with_retry(url: str, payload: dict) -> dict:
    """POST JSON a OpenRouter y retorna el body ya parseado.

    Reintenta hasta MAX_ATTEMPTS veces con backoff exponencial ante errores transitorios
    (429, 5xx o fallas de red). Un error 4xx distinto a 429 (ej. 401 por API key invalida)
    se considera irrecuperable y no se reintenta -- EXCEPTO el 402 "in_flight_budget_exhausted"
    (ver _is_in_flight_budget_error), que se reintenta aparte, hasta IN_FLIGHT_BUDGET_MAX_ATTEMPTS
    veces, respetando el Retry-After que manda OpenRouter.
    """
    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "HTTP-Referer": "http://localhost",
        "X-Title": "ecolex",
        "Content-Type": "application/json",
    }

    last_error_detail = "sin detalle"
    attempt = 0
    in_flight_attempt = 0

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as http_client:
        while True:
            try:
                response = await http_client.post(url, headers=headers, json=payload)
            except httpx.HTTPError as exc:
                last_error_detail = f"error de red: {exc}"
                attempt += 1
                logger.warning(
                    "Fallo de red llamando a OpenRouter (intento %d/%d): %s", attempt, MAX_ATTEMPTS, exc
                )
                if attempt >= MAX_ATTEMPTS:
                    break
                await asyncio.sleep(RETRY_BACKOFF_SECONDS[attempt - 1])
                continue

            if response.status_code == 200:
                return response.json()

            if _is_in_flight_budget_error(response):
                in_flight_attempt += 1
                if in_flight_attempt > IN_FLIGHT_BUDGET_MAX_ATTEMPTS:
                    last_error_detail = (
                        f"HTTP 402 (presupuesto de requests en vuelo agotado tras "
                        f"{in_flight_attempt - 1} esperas)"
                    )
                    break
                wait = _retry_after_seconds(response, IN_FLIGHT_BUDGET_DEFAULT_WAIT_SECONDS)
                logger.warning(
                    "OpenRouter: presupuesto de requests en vuelo agotado, esperando %.0fs antes "
                    "de reintentar (intento %d/%d)",
                    wait,
                    in_flight_attempt,
                    IN_FLIGHT_BUDGET_MAX_ATTEMPTS,
                )
                await asyncio.sleep(wait)
                continue

            last_error_detail = f"HTTP {response.status_code}: {response.text[:500]}"

            if response.status_code != 429 and response.status_code < 500:
                raise InternalServiceError(f"OpenRouter respondio {last_error_detail}")

            attempt += 1
            logger.warning(
                "OpenRouter respondio %d (intento %d/%d), reintentando",
                response.status_code,
                attempt,
                MAX_ATTEMPTS,
            )
            if attempt >= MAX_ATTEMPTS:
                break
            await asyncio.sleep(RETRY_BACKOFF_SECONDS[attempt - 1])

    raise InternalServiceError(f"OpenRouter fallo tras {attempt} intentos ({last_error_detail})")


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
