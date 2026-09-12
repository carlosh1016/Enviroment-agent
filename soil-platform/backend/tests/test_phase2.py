import io
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from conftest import TestSessionLocal
from docx import Document as DocxDocument
from sqlalchemy import select

from app.models.document import DocumentChunk
from app.models.user import User, UserRole
from app.services.auth_service import hash_password


def _unique_slug(prefix: str = "tenant") -> str:
    """Genera un slug unico de organizacion para evitar colisiones entre tests."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def _register(client, slug: str | None = None, email: str = "admin@example.com", password: str = "SecurePass123!"):
    slug = slug or _unique_slug()
    payload = {
        "tenant_name": "Empresa de Pruebas SAS",
        "tenant_slug": slug,
        "admin_email": email,
        "admin_password": password,
    }
    response = await client.post("/auth/register", json=payload)
    return response, slug


async def _login(client, email: str, password: str, tenant_slug: str | None = None):
    payload = {"email": email, "password": password}
    if tenant_slug:
        payload["tenant_slug"] = tenant_slug
    return await client.post("/auth/login", json=payload)


async def _register_and_login(client, email: str | None = None, password: str = "SecurePass123!"):
    """Registra un tenant + admin nuevo, inicia sesion y retorna los headers de Authorization y el slug."""
    email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
    _, slug = await _register(client, email=email, password=password)
    login_response = await _login(client, email, password, slug)
    token = login_response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}, slug


async def _get_tenant_id(client, headers: dict) -> uuid.UUID:
    response = await client.get("/auth/me", headers=headers)
    return uuid.UUID(response.json()["data"]["tenant_id"])


async def _create_additional_user(tenant_id: uuid.UUID, email: str, password: str, role: UserRole = UserRole.VIEWER) -> User:
    """Crea un segundo usuario directamente en DB para un tenant existente (no hay endpoint publico para esto)."""
    async with TestSessionLocal() as db:
        user = User(tenant_id=tenant_id, email=email, hashed_password=hash_password(password), role=role)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


def _make_minimal_pdf_bytes(text: str) -> bytes:
    """Construye un PDF minimo valido con un unico texto, sin depender de librerias de generacion de PDF."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
        b"/MediaBox [0 0 400 200] /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    stream_content = f"BT /F1 12 Tf 50 150 Td ({text}) Tj ET".encode("latin-1")
    objects.append(
        b"<< /Length " + str(len(stream_content)).encode() + b" >>\nstream\n" + stream_content + b"\nendstream"
    )

    buf = bytearray()
    buf += b"%PDF-1.4\n"
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(buf))
        buf += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"

    xref_offset = len(buf)
    buf += f"xref\n0 {len(objects) + 1}\n".encode()
    buf += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        buf += f"{off:010d} 00000 n \n".encode()
    buf += b"trailer\n"
    buf += f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode()
    buf += b"startxref\n"
    buf += f"{xref_offset}\n".encode()
    buf += b"%%EOF"

    return bytes(buf)


def _make_docx_bytes(text: str) -> bytes:
    doc = DocxDocument()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


VALID_PDF_TEXT = "Este es un documento de prueba sobre normativa ambiental colombiana y su aplicacion."
VALID_PDF_BYTES = _make_minimal_pdf_bytes(VALID_PDF_TEXT)
VALID_DOCX_BYTES = _make_docx_bytes(
    "Este es un documento DOCX de prueba sobre normativa ambiental colombiana y su aplicacion practica."
)
VALID_TXT_BYTES = (
    b"Contenido de prueba con mas de cincuenta caracteres sobre normativa ambiental colombiana. " * 3
)


def _mock_embeddings_instance(dim: int = 768, value: float = 0.1) -> MagicMock:
    """Crea un mock de GoogleGenerativeAIEmbeddings que retorna vectores deterministicos, sin llamadas reales."""
    instance = MagicMock()

    async def _aembed_documents(texts):
        return [[value] * dim for _ in texts]

    async def _aembed_query(text):
        return [value] * dim

    instance.aembed_documents = AsyncMock(side_effect=_aembed_documents)
    instance.aembed_query = AsyncMock(side_effect=_aembed_query)
    return instance


def _mock_chat_instance(response_text: str = "Respuesta simulada del asistente.") -> MagicMock:
    """Crea un mock de ChatGoogleGenerativeAI cuyo ainvoke retorna un texto fijo, sin llamadas reales."""
    instance = MagicMock()
    mock_response = MagicMock()
    mock_response.content = response_text
    instance.ainvoke = AsyncMock(return_value=mock_response)
    return instance


def _patched_ingestion_embeddings():
    return patch(
        "app.services.ingestion_service.GoogleGenerativeAIEmbeddings",
        return_value=_mock_embeddings_instance(),
    )


class TestDocumentUpload:
    async def test_upload_valid_pdf_returns_202_processing(self, client):
        """1. Upload de PDF valido debe retornar 202 con status='processing'."""
        headers, _ = await _register_and_login(client)

        with _patched_ingestion_embeddings():
            response = await client.post(
                "/api/v1/documents/upload",
                files={"file": ("normativa.pdf", VALID_PDF_BYTES, "application/pdf")},
                data={"es_base_corpus": "false"},
                headers=headers,
            )

        body = response.json()
        assert response.status_code == 202
        assert body["success"] is True
        assert body["data"]["status"] == "processing"
        assert body["data"]["filename"] == "normativa.pdf"

    async def test_upload_invalid_extension_returns_422(self, client):
        """2. Upload con extension invalida (.xlsx) debe retornar 422."""
        headers, _ = await _register_and_login(client)

        response = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("hoja.xlsx", b"contenido cualquiera", "application/vnd.ms-excel")},
            data={"es_base_corpus": "false"},
            headers=headers,
        )

        assert response.status_code == 422

    async def test_upload_file_too_large_returns_422(self, client):
        """3. Upload con archivo mayor a 10MB debe retornar 422."""
        headers, _ = await _register_and_login(client)

        oversized = b"a" * (10 * 1024 * 1024 + 1)
        response = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("grande.txt", oversized, "text/plain")},
            data={"es_base_corpus": "false"},
            headers=headers,
        )

        assert response.status_code == 422

    async def test_list_documents_only_shows_own_tenant(self, client):
        """4. Listar documentos del tenant solo debe mostrar los propios."""
        headers_a, _ = await _register_and_login(client, email="doc-a@example.com")
        headers_b, _ = await _register_and_login(client, email="doc-b@example.com")

        with _patched_ingestion_embeddings():
            await client.post(
                "/api/v1/documents/upload",
                files={"file": ("doc_a.txt", VALID_TXT_BYTES, "text/plain")},
                data={"es_base_corpus": "false"},
                headers=headers_a,
            )

        response_b = await client.get("/api/v1/documents/", headers=headers_b)
        assert response_b.status_code == 200
        assert response_b.json()["data"]["items"] == []

        response_a = await client.get("/api/v1/documents/", headers=headers_a)
        assert response_a.json()["data"]["total"] == 1

    async def test_get_document_from_other_tenant_returns_404(self, client):
        """5. GET documento por ID de otro tenant debe retornar 404."""
        headers_a, _ = await _register_and_login(client, email="doc-c@example.com")
        headers_b, _ = await _register_and_login(client, email="doc-d@example.com")

        with _patched_ingestion_embeddings():
            upload_response = await client.post(
                "/api/v1/documents/upload",
                files={"file": ("doc_c.txt", VALID_TXT_BYTES, "text/plain")},
                data={"es_base_corpus": "false"},
                headers=headers_a,
            )
        document_id = upload_response.json()["data"]["id"]

        response = await client.get(f"/api/v1/documents/{document_id}", headers=headers_b)
        assert response.status_code == 404

    async def test_delete_document_removes_document_and_chunks(self, client):
        """6. DELETE documento debe eliminar el documento y sus chunks (chunk_count=0 en DB tras el borrado)."""
        headers, _ = await _register_and_login(client, email="doc-e@example.com")

        with _patched_ingestion_embeddings():
            upload_response = await client.post(
                "/api/v1/documents/upload",
                files={"file": ("doc_e.txt", VALID_TXT_BYTES, "text/plain")},
                data={"es_base_corpus": "false"},
                headers=headers,
            )
        document_id = uuid.UUID(upload_response.json()["data"]["id"])

        detail_response = await client.get(f"/api/v1/documents/{document_id}", headers=headers)
        assert detail_response.json()["data"]["status"] == "ready"
        assert detail_response.json()["data"]["chunk_count"] > 0

        delete_response = await client.delete(f"/api/v1/documents/{document_id}", headers=headers)
        assert delete_response.status_code == 200

        get_after_delete = await client.get(f"/api/v1/documents/{document_id}", headers=headers)
        assert get_after_delete.status_code == 404

        async with TestSessionLocal() as db:
            result = await db.execute(select(DocumentChunk).where(DocumentChunk.document_id == document_id))
            remaining_chunks = result.scalars().all()
        assert len(remaining_chunks) == 0


class TestIngestionService:
    def test_parse_document_pdf_returns_non_empty_text(self):
        """7. parse_document con PDF valido debe retornar un string no vacio."""
        from app.services.ingestion_service import parse_document

        text = parse_document(VALID_PDF_BYTES, "pdf")
        assert len(text.strip()) > 0
        assert "normativa" in text.lower()

    def test_parse_document_docx_returns_non_empty_text(self):
        """8. parse_document con DOCX valido debe retornar un string no vacio."""
        from app.services.ingestion_service import parse_document

        text = parse_document(VALID_DOCX_BYTES, "docx")
        assert len(text.strip()) > 0
        assert "normativa" in text.lower()

    def test_chunk_text_generates_multiple_chunks_none_below_50_chars(self):
        """9. chunk_text con texto largo debe generar multiples chunks, ninguno menor a 50 caracteres."""
        from app.services.ingestion_service import chunk_text

        long_text = "Este parrafo trata sobre normativa ambiental colombiana y sus implicaciones. " * 50
        chunks = chunk_text(long_text, chunk_size=200, overlap=50)

        assert len(chunks) > 1
        assert all(len(chunk) >= 50 for chunk in chunks)


class TestRagRetrieval:
    async def test_retrieve_context_returns_chunks_of_correct_tenant(self, client):
        """10. retrieve_context con mock de embeddings debe retornar chunks solo del tenant correcto."""
        headers, _ = await _register_and_login(client, email="rag-a@example.com")
        tenant_id = await _get_tenant_id(client, headers)

        with _patched_ingestion_embeddings():
            await client.post(
                "/api/v1/documents/upload",
                files={"file": ("doc_rag.txt", VALID_TXT_BYTES, "text/plain")},
                data={"es_base_corpus": "false"},
                headers=headers,
            )

        from app.services.rag_service import retrieve_context

        async with TestSessionLocal() as db:
            with patch(
                "app.services.rag_service.GoogleGenerativeAIEmbeddings",
                return_value=_mock_embeddings_instance(),
            ):
                chunks = await retrieve_context(db, "normativa ambiental", tenant_id, k=5)

        assert len(chunks) > 0
        assert all(chunk.tenant_id == tenant_id for chunk in chunks)


class TestConversations:
    async def test_create_conversation_returns_201_with_id(self, client):
        """11. Crear conversacion debe retornar 201 con id."""
        headers, _ = await _register_and_login(client, email="conv-a@example.com")

        response = await client.post(
            "/api/v1/conversations/", json={"title": "Consulta sobre licencias"}, headers=headers
        )
        body = response.json()

        assert response.status_code == 201
        assert body["success"] is True
        assert "id" in body["data"]

    async def test_send_message_with_mocked_gemini_returns_assistant_response(self, client):
        """12. Enviar mensaje en conversacion con mocks de Gemini debe retornar 200 con respuesta del assistant."""
        headers, _ = await _register_and_login(client, email="conv-b@example.com")

        conv_response = await client.post("/api/v1/conversations/", json={}, headers=headers)
        conversation_id = conv_response.json()["data"]["id"]

        with (
            patch(
                "app.services.rag_service.GoogleGenerativeAIEmbeddings", return_value=_mock_embeddings_instance()
            ),
            patch(
                "app.services.rag_service.ChatGoogleGenerativeAI",
                return_value=_mock_chat_instance("La normativa vigente establece requisitos especificos."),
            ),
        ):
            response = await client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={"content": "Cual es la normativa sobre vertimientos?"},
                headers=headers,
            )

        body = response.json()
        assert response.status_code == 200
        assert body["data"]["role"] == "assistant"
        assert body["data"]["content"] == "La normativa vigente establece requisitos especificos."

    async def test_conversation_history_returns_chronological_order(self, client):
        """13. Historial de conversacion debe retornar los mensajes en orden cronologico."""
        headers, _ = await _register_and_login(client, email="conv-c@example.com")

        conv_response = await client.post("/api/v1/conversations/", json={}, headers=headers)
        conversation_id = conv_response.json()["data"]["id"]

        for reply in ("Respuesta 1", "Respuesta 2"):
            with (
                patch(
                    "app.services.rag_service.GoogleGenerativeAIEmbeddings",
                    return_value=_mock_embeddings_instance(),
                ),
                patch("app.services.rag_service.ChatGoogleGenerativeAI", return_value=_mock_chat_instance(reply)),
            ):
                await client.post(
                    f"/api/v1/conversations/{conversation_id}/messages",
                    json={"content": f"Pregunta para {reply}"},
                    headers=headers,
                )

        history_response = await client.get(f"/api/v1/conversations/{conversation_id}/messages", headers=headers)
        messages = history_response.json()["data"]

        assert len(messages) == 4
        timestamps = [m["created_at"] for m in messages]
        assert timestamps == sorted(timestamps)

    async def test_send_message_to_other_users_conversation_returns_403(self, client):
        """14. Enviar mensaje en conversacion de otro usuario del mismo tenant debe retornar 403."""
        headers_a, slug = await _register_and_login(client, email="conv-owner@example.com")
        tenant_id = await _get_tenant_id(client, headers_a)

        await _create_additional_user(tenant_id, "conv-intruder@example.com", "SecurePass123!")
        login_b = await _login(client, "conv-intruder@example.com", "SecurePass123!", slug)
        token_b = login_b.json()["data"]["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        conv_response = await client.post("/api/v1/conversations/", json={}, headers=headers_a)
        conversation_id = conv_response.json()["data"]["id"]

        response = await client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={"content": "Intento no autorizado"},
            headers=headers_b,
        )

        assert response.status_code == 403
