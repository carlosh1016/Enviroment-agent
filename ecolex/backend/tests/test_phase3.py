"""Tests de la Fase 3: generacion de reportes PDF de cumplimiento normativo a partir de una
conversacion. Mockea siempre generate_compliance_summary (llama a OpenRouter) y, salvo en el
test que ejercita build_pdf directamente, tambien build_pdf (WeasyPrint) para mantener los
tests rapidos y deterministas.
"""

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

from conftest import TestSessionLocal

from app.models.conversation import Conversation, Message, MessageRole


def _unique_slug(prefix: str = "tenant") -> str:
    """Genera un slug unico de organizacion para evitar colisiones entre tests."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def _register_and_login(client, email: str | None = None, password: str = "SecurePass123!"):
    """Registra un tenant + admin nuevo, inicia sesion y retorna (headers, tenant_id, user_id)."""
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
    headers = {"Authorization": f"Bearer {token}"}

    me_response = await client.get("/auth/me", headers=headers)
    me_data = me_response.json()["data"]
    return headers, uuid.UUID(me_data["tenant_id"]), uuid.UUID(me_data["id"])


async def _create_conversation_with_messages(
    tenant_id: uuid.UUID, user_id: uuid.UUID, entries: list[tuple]
) -> uuid.UUID:
    """Crea una conversacion y sus mensajes directamente en DB. `entries` es una lista de
    (role, content, created_at, source_chunks)."""
    async with TestSessionLocal() as db:
        conversation = Conversation(tenant_id=tenant_id, user_id=user_id, title=None)
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)

        for role, content, created_at, source_chunks in entries:
            db.add(
                Message(
                    tenant_id=tenant_id,
                    conversation_id=conversation.id,
                    role=role,
                    content=content,
                    source_chunks=source_chunks,
                    created_at=created_at,
                )
            )
        await db.commit()

        return conversation.id


def _dt(day: int) -> datetime:
    return datetime(2026, 1, day, 10, 0, tzinfo=timezone.utc)


def _patched_summary(text: str = "1. SÍNTESIS EJECUTIVA\nResumen de prueba."):
    return patch(
        "app.services.report_service.generate_compliance_summary", new=AsyncMock(return_value=text)
    )


def _patched_pdf(pdf_bytes: bytes = b"%PDF-fake-content"):
    return patch("app.services.report_service.build_pdf", new=AsyncMock(return_value=pdf_bytes))


class TestBuildPdf:
    async def test_generate_report_returns_pdf_bytes(self):
        """1. build_pdf con datos de prueba debe devolver bytes que empiecen con %PDF."""
        from app.services.report_service import build_pdf

        conversation = Conversation(id=uuid.uuid4(), tenant_id=uuid.uuid4(), title="Consulta sobre vertimientos")
        messages = [
            Message(
                id=uuid.uuid4(),
                tenant_id=conversation.tenant_id,
                conversation_id=conversation.id,
                role=MessageRole.USER,
                content="Que se necesita para verter aguas residuales?",
                source_chunks=None,
                created_at=_dt(1),
            ),
            Message(
                id=uuid.uuid4(),
                tenant_id=conversation.tenant_id,
                conversation_id=conversation.id,
                role=MessageRole.ASSISTANT,
                content="Se requiere un permiso de vertimientos segun el articulo 5.",
                source_chunks=[
                    {
                        "document_id": str(uuid.uuid4()),
                        "chunk_index": 0,
                        "score": 0.9,
                        "numero_articulo": "5",
                        "pagina_origen": 1,
                        "document_name": "Decreto 1076 de 2015.pdf",
                    }
                ],
                created_at=_dt(1),
            ),
        ]
        summary = (
            "1. SÍNTESIS EJECUTIVA\nSe realizaron consultas sobre vertimientos.\n\n"
            "2. NORMAS CONSULTADAS\nDecreto 1076 de 2015 (1 vez).\n\n"
            "3. OBLIGACIONES IDENTIFICADAS\nObtener permiso de vertimientos.\n\n"
            "4. BRECHAS POTENCIALES DE CUMPLIMIENTO\nNinguna identificada.\n\n"
            "5. RECOMENDACIONES\nTramitar el permiso correspondiente."
        )

        pdf_bytes = await build_pdf(
            conversation, messages, summary, "Empresa de Pruebas SAS", date(2026, 1, 1), date(2026, 1, 1)
        )

        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes.startswith(b"%PDF")


class TestReportEndpoint:
    async def test_report_endpoint_returns_200_with_pdf(self, client):
        """2. POST /reports/conversations/{id} con >=2 mensajes debe devolver 200 y un PDF."""
        headers, tenant_id, user_id = await _register_and_login(client, email="report-a@example.com")
        conversation_id = await _create_conversation_with_messages(
            tenant_id,
            user_id,
            [
                (MessageRole.USER, "Pregunta 1", _dt(1), None),
                (MessageRole.ASSISTANT, "Respuesta 1", _dt(1), None),
            ],
        )

        with _patched_summary(), _patched_pdf():
            response = await client.post(
                f"/api/v1/reports/conversations/{conversation_id}", json={}, headers=headers
            )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert "attachment" in response.headers["content-disposition"]

    async def test_report_endpoint_too_few_messages_returns_422(self, client):
        """3. Con un solo mensaje debe devolver 422 con el mensaje de error correcto, sin
        llamar a generate_compliance_summary."""
        headers, tenant_id, user_id = await _register_and_login(client, email="report-b@example.com")
        conversation_id = await _create_conversation_with_messages(
            tenant_id, user_id, [(MessageRole.USER, "Unica pregunta", _dt(1), None)]
        )

        with _patched_summary() as mock_summary:
            response = await client.post(
                f"/api/v1/reports/conversations/{conversation_id}", json={}, headers=headers
            )

        assert response.status_code == 422
        assert response.json()["message"] == "Se necesitan al menos 2 mensajes para generar un informe"
        mock_summary.assert_not_called()

    async def test_report_endpoint_wrong_tenant_returns_403(self, client):
        """4. Generar un informe de una conversacion de otro tenant debe devolver 403."""
        _, tenant_a_id, user_a_id = await _register_and_login(client, email="report-owner@example.com")
        headers_b, _, _ = await _register_and_login(client, email="report-intruder@example.com")

        conversation_id = await _create_conversation_with_messages(
            tenant_a_id,
            user_a_id,
            [
                (MessageRole.USER, "Pregunta 1", _dt(1), None),
                (MessageRole.ASSISTANT, "Respuesta 1", _dt(1), None),
            ],
        )

        with _patched_summary(), _patched_pdf():
            response = await client.post(
                f"/api/v1/reports/conversations/{conversation_id}", json={}, headers=headers_b
            )

        assert response.status_code == 403

    async def test_date_range_filters_messages(self, client):
        """5. Con date_from/date_to que solo cubren un par de mensajes, generate_compliance_summary
        debe ser llamado con exactamente esos 2 mensajes."""
        headers, tenant_id, user_id = await _register_and_login(client, email="report-dates@example.com")
        conversation_id = await _create_conversation_with_messages(
            tenant_id,
            user_id,
            [
                (MessageRole.USER, "Pregunta enero", _dt(1), None),
                (MessageRole.ASSISTANT, "Respuesta enero", _dt(1), None),
                (MessageRole.USER, "Pregunta junio", datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc), None),
                (MessageRole.ASSISTANT, "Respuesta junio", datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc), None),
            ],
        )

        with _patched_summary() as mock_summary, _patched_pdf():
            response = await client.post(
                f"/api/v1/reports/conversations/{conversation_id}",
                json={"date_from": "2026-01-01", "date_to": "2026-01-01"},
                headers=headers,
            )

        assert response.status_code == 200
        mock_summary.assert_called_once()
        filtered_messages = mock_summary.call_args.args[0]
        assert len(filtered_messages) == 2
        assert {m.content for m in filtered_messages} == {"Pregunta enero", "Respuesta enero"}
