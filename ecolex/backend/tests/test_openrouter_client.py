"""Tests del manejo de reintentos de app/services/openrouter_client.py, en particular el 402
"in_flight_budget_exhausted" que se observo en vivo durante la sincronizacion de Minambiente
(2026-10-26): un presupuesto de requests EN VUELO bajo (ligado al limite configurado en la API
key, no al saldo real) rechaza requests normales y transitorias, y OpenRouter pide reintentar
respetando el header Retry-After. Antes de este fix, ese 402 se trataba como fallo permanente
(sin reintento), tumbando ~30 de 40 documentos en una sola corrida real."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.openrouter_client import InternalServiceError, _post_with_retry


def _response(status_code: int, json_body: dict | None = None, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(status_code=status_code, json=json_body or {}, headers=headers or {})


def _in_flight_402(retry_after: str | None = "0") -> httpx.Response:
    body = {"error": {"message": "...", "code": 402, "metadata": {"reason": "in_flight_budget_exhausted"}}}
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    return _response(402, body, headers)


class TestInFlightBudgetRetry:
    async def test_retries_and_eventually_succeeds(self):
        responses = [_in_flight_402(), _in_flight_402(), _response(200, {"ok": True})]

        with (
            patch.object(httpx.AsyncClient, "post", new=AsyncMock(side_effect=responses)) as mock_post,
            patch("app.services.openrouter_client.asyncio.sleep", new=AsyncMock()) as mock_sleep,
        ):
            result = await _post_with_retry("https://example.test/x", {"foo": "bar"})

        assert result == {"ok": True}
        assert mock_post.call_count == 3
        mock_sleep.assert_awaited()

    async def test_honours_retry_after_header(self):
        responses = [_in_flight_402(retry_after="7"), _response(200, {"ok": True})]

        with (
            patch.object(httpx.AsyncClient, "post", new=AsyncMock(side_effect=responses)),
            patch("app.services.openrouter_client.asyncio.sleep", new=AsyncMock()) as mock_sleep,
        ):
            await _post_with_retry("https://example.test/x", {})

        mock_sleep.assert_awaited_once_with(7.0)

    async def test_missing_retry_after_falls_back_to_default(self):
        responses = [_in_flight_402(retry_after=None), _response(200, {"ok": True})]

        with (
            patch.object(httpx.AsyncClient, "post", new=AsyncMock(side_effect=responses)),
            patch("app.services.openrouter_client.asyncio.sleep", new=AsyncMock()) as mock_sleep,
        ):
            await _post_with_retry("https://example.test/x", {})

        mock_sleep.assert_awaited_once_with(120.0)

    async def test_gives_up_after_max_attempts(self):
        responses = [_in_flight_402() for _ in range(10)]

        with (
            patch.object(httpx.AsyncClient, "post", new=AsyncMock(side_effect=responses)) as mock_post,
            patch("app.services.openrouter_client.asyncio.sleep", new=AsyncMock()),
            pytest.raises(InternalServiceError),
        ):
            await _post_with_retry("https://example.test/x", {})

        # IN_FLIGHT_BUDGET_MAX_ATTEMPTS (4) reintentos + el intento original = 5 llamadas
        assert mock_post.call_count == 5

    async def test_other_402_reason_is_not_retried(self):
        """Un 402 por otro motivo (ej. saldo real insuficiente) es un fallo permanente, no
        transitorio: no debe reintentarse."""
        body = {"error": {"message": "insufficient credits", "code": 402, "metadata": {"reason": "insufficient_credits"}}}
        responses = [_response(402, body)]

        with (
            patch.object(httpx.AsyncClient, "post", new=AsyncMock(side_effect=responses)) as mock_post,
            pytest.raises(InternalServiceError),
        ):
            await _post_with_retry("https://example.test/x", {})

        assert mock_post.call_count == 1

    async def test_402_without_json_body_is_not_retried(self):
        responses = [httpx.Response(status_code=402, text="not json")]

        with (
            patch.object(httpx.AsyncClient, "post", new=AsyncMock(side_effect=responses)) as mock_post,
            pytest.raises(InternalServiceError),
        ):
            await _post_with_retry("https://example.test/x", {})

        assert mock_post.call_count == 1


class TestExistingRetryBehaviourUnchanged:
    async def test_429_still_retries_with_short_backoff(self):
        responses = [_response(429), _response(200, {"ok": True})]

        with (
            patch.object(httpx.AsyncClient, "post", new=AsyncMock(side_effect=responses)),
            patch("app.services.openrouter_client.asyncio.sleep", new=AsyncMock()) as mock_sleep,
        ):
            result = await _post_with_retry("https://example.test/x", {})

        assert result == {"ok": True}
        mock_sleep.assert_awaited_once_with(2)

    async def test_401_is_not_retried(self):
        responses = [_response(401, {"error": "unauthorized"})]

        with (
            patch.object(httpx.AsyncClient, "post", new=AsyncMock(side_effect=responses)) as mock_post,
            pytest.raises(InternalServiceError),
        ):
            await _post_with_retry("https://example.test/x", {})

        assert mock_post.call_count == 1

    async def test_network_error_retries_up_to_max_attempts(self):
        with (
            patch.object(httpx.AsyncClient, "post", new=AsyncMock(side_effect=httpx.ConnectError("boom"))) as mock_post,
            patch("app.services.openrouter_client.asyncio.sleep", new=AsyncMock()),
            pytest.raises(InternalServiceError),
        ):
            await _post_with_retry("https://example.test/x", {})

        assert mock_post.call_count == 3
