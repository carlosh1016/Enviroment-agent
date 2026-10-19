import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_tenant
from app.models.conversation import Conversation, Message, MessageRole
from app.models.document import Document, DocumentFileType, DocumentStatus
from app.models.tenant import Tenant
from app.schemas import success_response
from app.schemas.stats import CitedDocument, DashboardStats, DayActivity

router = APIRouter(prefix="/api/v1/stats", tags=["stats"])

ACTIVITY_WINDOW_DAYS = 14
TOP_CITED_LIMIT = 5


@router.get("/dashboard")
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Agregados para las graficas del dashboard, siempre acotados al tenant actual (nunca se
    cruzan datos entre tenants).

    documents_by_status/documents_by_type excluyen el corpus base compartido (is_base_corpus),
    igual que GET /documents (el corpus base nunca aparece ahi). top_cited_documents SI puede
    incluir documentos del corpus base: refleja que normas consulto mas el equipo de este
    tenant al chatear, sean documentos propios o del corpus compartido.
    """
    own_docs_result = await db.execute(
        select(Document.status, Document.file_type).where(
            Document.tenant_id == tenant.id, Document.is_base_corpus.is_(False)
        )
    )
    own_docs = own_docs_result.all()
    status_counts = Counter(doc_status.value for doc_status, _ in own_docs)
    type_counts = Counter(file_type.value for _, file_type in own_docs)
    # Incluye todos los status/tipos posibles en 0, no solo los que tienen documentos: una
    # grafica de barras/dona con una categoria faltante en vez de en 0 se ve como un error.
    documents_by_status = {s.value: status_counts.get(s.value, 0) for s in DocumentStatus}
    documents_by_type = {t.value: type_counts.get(t.value, 0) for t in DocumentFileType}

    cutoff = datetime.now(timezone.utc) - timedelta(days=ACTIVITY_WINDOW_DAYS - 1)
    conv_result = await db.execute(
        select(Conversation.created_at).where(Conversation.tenant_id == tenant.id, Conversation.created_at >= cutoff)
    )
    msg_result = await db.execute(
        select(Message.created_at).where(Message.tenant_id == tenant.id, Message.created_at >= cutoff)
    )
    # El bucketing por dia se hace en Python (no con funciones de fecha especificas de
    # Postgres como date_trunc) para que esta query funcione igual en SQLite (tests).
    conv_by_day = Counter(created_at.date() for (created_at,) in conv_result.all())
    msg_by_day = Counter(created_at.date() for (created_at,) in msg_result.all())

    today = datetime.now(timezone.utc).date()
    activity = [
        DayActivity(
            date=(day := today - timedelta(days=offset)),
            conversations=conv_by_day.get(day, 0),
            messages=msg_by_day.get(day, 0),
        )
        for offset in range(ACTIVITY_WINDOW_DAYS - 1, -1, -1)
    ]

    messages_result = await db.execute(
        select(Message.source_chunks).where(
            Message.tenant_id == tenant.id,
            Message.role == MessageRole.ASSISTANT,
            Message.source_chunks.is_not(None),
        )
    )
    citation_counts: Counter[str] = Counter()
    for (source_chunks,) in messages_result.all():
        for chunk in source_chunks or []:
            document_id = chunk.get("document_id")
            if document_id:
                citation_counts[document_id] += 1

    top_items = citation_counts.most_common(TOP_CITED_LIMIT)
    top_document_ids = [uuid.UUID(document_id) for document_id, _ in top_items]
    filenames: dict[uuid.UUID, str] = {}
    if top_document_ids:
        names_result = await db.execute(select(Document.id, Document.filename).where(Document.id.in_(top_document_ids)))
        filenames = {document_id: filename for document_id, filename in names_result.all()}

    top_cited_documents = [
        CitedDocument(
            document_id=uuid.UUID(document_id),
            document_name=filenames.get(uuid.UUID(document_id), "Documento eliminado"),
            citations=count,
        )
        for document_id, count in top_items
    ]

    stats = DashboardStats(
        documents_by_status=documents_by_status,
        documents_by_type=documents_by_type,
        activity_last_14_days=activity,
        top_cited_documents=top_cited_documents,
    )
    return success_response(data=stats.model_dump(mode="json"), message="Estadisticas obtenidas exitosamente")
