"""Tests de app/services/minambiente_sync_service.py, en particular que una norma marcada
'failed' (ej. por el 402 transitorio de OpenRouter, ver test_openrouter_client.py) sea
retomada en la siguiente corrida en vez de quedar bloqueada para siempre por el dedupe de
pdf_url (bug real observado el 2026-10-26: 30 de 40 documentos de una corrida quedaron
'failed' y ninguna corrida futura los iba a volver a intentar)."""

import uuid
from datetime import date
from pathlib import Path

import pytest
from conftest import TestSessionLocal

from app.models.document import Document, DocumentFileType, DocumentStatus
from app.models.external_norm import ExternalNorm, ExternalNormSource, ExternalNormStatus
from app.models.tenant import Tenant
from app.services.minambiente_sync_service import (
    STORAGE_DIR,
    _extract_norm_identity,
    _get_or_create_external_norm,
    _load_base_corpus_identities,
)

ENTRY = {
    "title": "Decreto 1553 del 23 de Diciembre de 2024",
    "pdf_url": "https://www.minambiente.gov.co/wp-content/uploads/2024/12/Decreto-1553.pdf",
    "published_at": date(2024, 12, 23),
}


@pytest.fixture
async def db():
    async with TestSessionLocal() as session:
        yield session


class TestRetryOfFailedNorms:
    async def test_brand_new_entry_is_a_candidate(self, db):
        norm, is_candidate = await _get_or_create_external_norm(db, "decretos", ENTRY, {})
        await db.commit()

        assert is_candidate is True
        assert norm.status == ExternalNormStatus.PENDING

    async def test_ingested_entry_is_not_retried(self, db):
        existing = ExternalNorm(
            source=ExternalNormSource.MINAMBIENTE,
            category="decretos",
            title=ENTRY["title"],
            pdf_url=ENTRY["pdf_url"],
            status=ExternalNormStatus.INGESTED,
        )
        db.add(existing)
        await db.commit()

        norm, is_candidate = await _get_or_create_external_norm(db, "decretos", ENTRY, {})

        assert is_candidate is False
        assert norm.status == ExternalNormStatus.INGESTED

    async def test_pending_entry_with_stuck_document_is_retried(self, db, tmp_path, monkeypatch):
        """Una fila en PENDING con el Document aun en 'processing' solo puede existir si el
        proceso se interrumpio a medio commit (ej. el proceso matado por falta de memoria del
        sistema, visto en vivo el 2026-10-26) -- debe reintentarse, igual que 'failed'."""
        monkeypatch.setattr("app.services.minambiente_sync_service.STORAGE_DIR", tmp_path)

        tenant = Tenant(name="Base", slug=f"_base-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()

        stuck_document = Document(
            tenant_id=tenant.id,
            filename="Decreto-1553.pdf",
            file_type=DocumentFileType.PDF,
            file_size_bytes=1234,
            status=DocumentStatus.PROCESSING,
            is_base_corpus=True,
        )
        db.add(stuck_document)
        await db.flush()

        existing = ExternalNorm(
            source=ExternalNormSource.MINAMBIENTE,
            category="decretos",
            title=ENTRY["title"],
            pdf_url=ENTRY["pdf_url"],
            status=ExternalNormStatus.PENDING,
            document_id=stuck_document.id,
        )
        db.add(existing)
        await db.commit()

        norm, is_candidate = await _get_or_create_external_norm(db, "decretos", ENTRY, {})
        await db.commit()

        assert is_candidate is True
        assert norm.id == existing.id
        assert norm.document_id is None
        remaining = await db.get(Document, stuck_document.id)
        assert remaining is None

    async def test_failed_entry_without_document_is_retried(self, db):
        existing = ExternalNorm(
            source=ExternalNormSource.MINAMBIENTE,
            category="decretos",
            title=ENTRY["title"],
            pdf_url=ENTRY["pdf_url"],
            status=ExternalNormStatus.FAILED,
            error_message="OpenRouter respondio HTTP 402: ...",
        )
        db.add(existing)
        await db.commit()

        norm, is_candidate = await _get_or_create_external_norm(db, "decretos", ENTRY, {})
        await db.commit()

        assert is_candidate is True
        assert norm.status == ExternalNormStatus.PENDING
        assert norm.error_message is None
        # Sigue siendo la MISMA fila (no se duplica por pdf_url): sin esto, external_norms
        # terminaria con dos filas para el mismo pdf_url al reintentar.
        assert norm.id == existing.id

    async def test_failed_entry_with_broken_document_is_cleaned_up_and_retried(self, db, tmp_path, monkeypatch):
        """El Document de una ingesta fallida (status FAILED, 0 chunks) no debe quedar huerfano
        en disco ni en la DB cuando se reintenta -- se borra antes de reintentar, igual que se
        hizo manualmente con el documento que quedo atascado tras matar el job el 2026-10-21."""
        monkeypatch.setattr("app.services.minambiente_sync_service.STORAGE_DIR", tmp_path)

        tenant = Tenant(name="Base", slug=f"_base-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()

        broken_document = Document(
            tenant_id=tenant.id,
            filename="Decreto-1553.pdf",
            file_type=DocumentFileType.PDF,
            file_size_bytes=1234,
            status=DocumentStatus.ERROR,
            is_base_corpus=True,
        )
        db.add(broken_document)
        await db.flush()

        stale_file = tmp_path / f"{broken_document.id}.pdf"
        stale_file.write_bytes(b"%PDF-fake")

        existing = ExternalNorm(
            source=ExternalNormSource.MINAMBIENTE,
            category="decretos",
            title=ENTRY["title"],
            pdf_url=ENTRY["pdf_url"],
            status=ExternalNormStatus.FAILED,
            error_message="OpenRouter respondio HTTP 402: ...",
            document_id=broken_document.id,
        )
        db.add(existing)
        await db.commit()

        norm, is_candidate = await _get_or_create_external_norm(db, "decretos", ENTRY, {})
        await db.commit()

        assert is_candidate is True
        assert norm.document_id is None
        assert not stale_file.exists()

        remaining = await db.get(Document, broken_document.id)
        assert remaining is None


class TestNormIdentityExtraction:
    """Ver _extract_norm_identity: el titulo mostrado en pantalla por Minambiente y el nombre de
    archivo real de un documento cargado a mano se escriben distinto (espacios vs guiones/
    guiones bajos, con o sin ceros a la izquierda, con o sin tilde), pero deben reconocerse como
    la MISMA norma."""

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Decreto 1076 de 2015", ("decreto", 1076, 2015)),
            (
                "Decreto_1076_de_2015_Sector_Ambiente_y_Desarrollo_Sostenible.pdf",
                ("decreto", 1076, 2015),
            ),
            (
                "Guía Informativa_ Estructura y Regulación del Sector Ambiente y Desarrollo "
                "Sostenible (Decreto 1076 de 2015).pdf",
                ("decreto", 1076, 2015),
            ),
            ("resolucion-0316-de-2018.pdf", ("resolucion", 316, 2018)),
            ("Resolucion-0627-de-2006.pdf", ("resolucion", 627, 2006)),
            ("Resolución No. 0861 de 2011", ("resolucion", 861, 2011)),
            ("Nada que ver con una norma", None),
        ],
    )
    def test_extracts_expected_identity(self, text, expected):
        assert _extract_norm_identity(text) == expected


class TestDuplicateAgainstBaseCorpus:
    """Bug real observado el 2026-10-26: Minambiente lista 'Decreto 1076 de 2015' en su propia
    pagina de decretos, y el scraper lo iba a re-ingestar (gastando OpenRouter) como si fuera
    nuevo, aunque ya estaba en el corpus desde la carga manual inicial bajo un pdf_url distinto."""

    async def test_load_base_corpus_identities_maps_existing_documents(self, db):
        tenant = Tenant(name="Base", slug=f"_base-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()

        document = Document(
            tenant_id=tenant.id,
            filename="Decreto_1076_de_2015_Sector_Ambiente_y_Desarrollo_Sostenible.pdf",
            file_type=DocumentFileType.PDF,
            file_size_bytes=1,
            status=DocumentStatus.READY,
            is_base_corpus=True,
        )
        db.add(document)
        await db.commit()

        identities = await _load_base_corpus_identities(db, tenant.id)

        assert identities == {("decreto", 1076, 2015): document.id}

    async def test_new_entry_matching_base_corpus_is_linked_not_ingested(self, db):
        tenant = Tenant(name="Base", slug=f"_base-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()

        existing_document = Document(
            tenant_id=tenant.id,
            filename="Decreto_1076_de_2015_Sector_Ambiente_y_Desarrollo_Sostenible.pdf",
            file_type=DocumentFileType.PDF,
            file_size_bytes=1,
            status=DocumentStatus.READY,
            is_base_corpus=True,
        )
        db.add(existing_document)
        await db.commit()

        entry = {
            "title": "Decreto 1076 de 2015",
            "pdf_url": "https://www.minambiente.gov.co/wp-content/uploads/2021/06/Decreto-1076-de-2015.pdf",
            "published_at": date(2015, 5, 26),
        }
        identities = await _load_base_corpus_identities(db, tenant.id)

        norm, is_candidate = await _get_or_create_external_norm(db, "decretos", entry, identities)
        await db.commit()

        assert is_candidate is False
        assert norm.status == ExternalNormStatus.INGESTED
        assert norm.document_id == existing_document.id

    async def test_new_entry_without_match_is_still_a_candidate(self, db):
        """Control: una norma sin equivalente en el corpus base debe seguir su camino normal
        (candidata a descargarse e ingestarse), el cruce no debe bloquear nada que no sea un
        duplicado real."""
        tenant = Tenant(name="Base", slug=f"_base-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()

        document = Document(
            tenant_id=tenant.id,
            filename="Decreto_1076_de_2015_Sector_Ambiente_y_Desarrollo_Sostenible.pdf",
            file_type=DocumentFileType.PDF,
            file_size_bytes=1,
            status=DocumentStatus.READY,
            is_base_corpus=True,
        )
        db.add(document)
        await db.commit()

        identities = await _load_base_corpus_identities(db, tenant.id)

        norm, is_candidate = await _get_or_create_external_norm(db, "decretos", ENTRY, identities)
        await db.commit()

        assert is_candidate is True
        assert norm.status == ExternalNormStatus.PENDING
        assert norm.document_id is None
