"""Tests del query-side del RAG (Fase 2 parte 2): sesiones de conversacion con memoria,
recuperacion de chunks relevantes con umbral de score, y generacion de respuesta via
OpenRouter. Mockea openrouter_client y los embeddings en todos los tests: no hace llamadas
externas reales.

Nota sobre el esquema: este proyecto usa un unico nivel de multi-tenant (tenant_id), no
organization_id/project_id. Una "sesion de conversacion" es el modelo Conversation existente
(app/models/conversation.py) expuesto en /api/v1/conversations/.
"""

import uuid
from unittest.mock import AsyncMock, patch


def _unique_slug(prefix: str = "tenant") -> str:
    """Genera un slug unico de organizacion para evitar colisiones entre tests."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def _register_and_login(client, email: str | None = None, password: str = "SecurePass123!"):
    """Registra un tenant + admin nuevo, inicia sesion y retorna los headers de Authorization."""
    email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
    slug = _unique_slug()
    await client.post(
        "/auth/register",
        json={
            "tenant_name": "Empresa de Pruebas SAS",
            "tenant_slug": slug,
            "admin_email": email,
            "admin_password": password,
        },
    )
    login_response = await client.post(
        "/auth/login", json={"email": email, "password": password, "tenant_slug": slug}
    )
    token = login_response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _mock_chunk(
    document_id: uuid.UUID | None = None,
    chunk_index: int = 0,
    score: float = 0.9,
    numero_articulo: str | None = "5",
    pagina_origen: int | None = 1,
    content: str = "El articulo 5 establece los requisitos de licenciamiento ambiental.",
) -> dict:
    """Construye un dict con la forma exacta que retorna rag_service.retrieve_relevant_chunks."""
    return {
        "content": content,
        "score": score,
        "document_id": document_id or uuid.uuid4(),
        "chunk_index": chunk_index,
        "numero_articulo": numero_articulo,
        "pagina_origen": pagina_origen,
    }


def _patched_title_generation(title: str = "Consulta sobre licenciamiento ambiental"):
    """Mockea la llamada a OpenRouter para el titulo automatico de la sesion (sin red real)."""
    return patch(
        "app.services.rag_service.openrouter_client.chat_completion",
        new=AsyncMock(return_value=title),
    )


class TestConversationSessions:
    async def test_create_session_returns_201(self, client):
        """1. Crear una sesion de conversacion debe retornar 201 con session_id y tenant_id."""
        headers = await _register_and_login(client, email="rag-session-a@example.com")

        response = await client.post("/api/v1/conversations/", json={}, headers=headers)
        body = response.json()

        assert response.status_code == 201
        assert body["success"] is True
        assert "id" in body["data"]
        assert "tenant_id" in body["data"]

    async def test_send_message_to_other_tenants_session_returns_403(self, client):
        """2. Enviar un mensaje a una sesion que pertenece a otro usuario/tenant debe fallar.

        No existe un endpoint de creacion de sesiones que reciba un project_id/organization_id
        ajeno para spoofear (una conversacion nace siempre bajo el tenant del usuario
        autenticado), asi que el escenario equivalente de aislamiento es acceder a una sesion
        de OTRO tenant ya creada.
        """
        headers_owner = await _register_and_login(client, email="rag-session-owner@example.com")
        headers_intruder = await _register_and_login(client, email="rag-session-intruder@example.com")

        session_response = await client.post("/api/v1/conversations/", json={}, headers=headers_owner)
        session_id = session_response.json()["data"]["id"]

        response = await client.post(
            f"/api/v1/conversations/{session_id}/messages",
            json={"content": "Intento no autorizado"},
            headers=headers_intruder,
        )

        assert response.status_code in (403, 404)


class TestSendMessage:
    async def test_send_message_no_chunks_returns_fallback(self, client):
        """3. Si no hay chunks relevantes, el asistente responde el mensaje de fallback y lo
        guarda en DB con role='assistant', sin llamar a generate_response."""
        headers = await _register_and_login(client, email="rag-fallback@example.com")

        session_response = await client.post("/api/v1/conversations/", json={}, headers=headers)
        session_id = session_response.json()["data"]["id"]

        with (
            patch("app.services.rag_service.retrieve_relevant_chunks", new=AsyncMock(return_value=[])),
            patch("app.services.rag_service.generate_response", new=AsyncMock()) as mock_generate,
            _patched_title_generation(),
        ):
            response = await client.post(
                f"/api/v1/conversations/{session_id}/messages",
                json={"content": "Pregunta sin respuesta en el corpus"},
                headers=headers,
            )

        body = response.json()
        assert response.status_code == 200
        assert body["data"]["role"] == "assistant"
        assert "No encontré información relevante" in body["data"]["content"]
        assert body["data"]["source_chunks"] in (None, [])
        mock_generate.assert_not_called()

    async def test_send_message_with_chunks_returns_response(self, client):
        """4. Con chunks relevantes, retorna 200 con content no vacio y sources con 2 entradas."""
        headers = await _register_and_login(client, email="rag-with-chunks@example.com")

        session_response = await client.post("/api/v1/conversations/", json={}, headers=headers)
        session_id = session_response.json()["data"]["id"]

        chunks = [
            _mock_chunk(chunk_index=0, numero_articulo="5", pagina_origen=1),
            _mock_chunk(chunk_index=1, numero_articulo="6", pagina_origen=2),
        ]

        with (
            patch("app.services.rag_service.retrieve_relevant_chunks", new=AsyncMock(return_value=chunks)),
            patch(
                "app.services.rag_service.generate_response",
                new=AsyncMock(return_value="El articulo 5 establece los requisitos de licenciamiento."),
            ),
            _patched_title_generation(),
        ):
            response = await client.post(
                f"/api/v1/conversations/{session_id}/messages",
                json={"content": "Cuales son los requisitos de licenciamiento?"},
                headers=headers,
            )

        body = response.json()
        assert response.status_code == 200
        assert len(body["data"]["content"]) > 0
        assert len(body["data"]["source_chunks"]) == 2


class TestConversationHistory:
    async def test_history_is_included_in_second_message(self, client):
        """5. Al enviar un segundo mensaje, generate_response debe recibir el historial con
        al menos 2 mensajes (el primer par user/assistant)."""
        headers = await _register_and_login(client, email="rag-history@example.com")

        session_response = await client.post("/api/v1/conversations/", json={}, headers=headers)
        session_id = session_response.json()["data"]["id"]

        chunks = [_mock_chunk()]

        with (
            patch("app.services.rag_service.retrieve_relevant_chunks", new=AsyncMock(return_value=chunks)),
            patch(
                "app.services.rag_service.generate_response", new=AsyncMock(return_value="Respuesta 1")
            ) as mock_generate,
            _patched_title_generation(),
        ):
            await client.post(
                f"/api/v1/conversations/{session_id}/messages",
                json={"content": "Primera pregunta"},
                headers=headers,
            )

        with (
            patch("app.services.rag_service.retrieve_relevant_chunks", new=AsyncMock(return_value=chunks)),
            patch(
                "app.services.rag_service.generate_response", new=AsyncMock(return_value="Respuesta 2")
            ) as mock_generate,
            _patched_title_generation(),
        ):
            await client.post(
                f"/api/v1/conversations/{session_id}/messages",
                json={"content": "Segunda pregunta"},
                headers=headers,
            )

        assert mock_generate.call_count == 1
        history_arg = mock_generate.call_args.args[2]
        assert len(history_arg) >= 2

    async def test_get_messages_returns_ordered_list(self, client):
        """6. GET /messages debe devolver los mensajes ordenados por created_at, con role
        alternado user/assistant."""
        headers = await _register_and_login(client, email="rag-get-messages@example.com")

        session_response = await client.post("/api/v1/conversations/", json={}, headers=headers)
        session_id = session_response.json()["data"]["id"]

        chunks = [_mock_chunk()]
        for question, reply in (("Pregunta 1", "Respuesta 1"), ("Pregunta 2", "Respuesta 2")):
            with (
                patch("app.services.rag_service.retrieve_relevant_chunks", new=AsyncMock(return_value=chunks)),
                patch("app.services.rag_service.generate_response", new=AsyncMock(return_value=reply)),
                _patched_title_generation(),
            ):
                await client.post(
                    f"/api/v1/conversations/{session_id}/messages",
                    json={"content": question},
                    headers=headers,
                )

        response = await client.get(f"/api/v1/conversations/{session_id}/messages", headers=headers)
        messages = response.json()["data"]

        assert len(messages) == 4
        timestamps = [m["created_at"] for m in messages]
        assert timestamps == sorted(timestamps)
        assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]
