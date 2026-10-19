import io
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_tenant, get_current_user
from app.models.conversation import Message
from app.models.tenant import Tenant
from app.models.user import User
from app.routers.conversations import _get_viewable_conversation_or_404
from app.schemas.report import ReportRequest
from app.services import report_service
from app.services.rag_service import _get_document_filenames

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

MIN_MESSAGES_FOR_REPORT = 2
TOO_FEW_MESSAGES_DETAIL = "Se necesitan al menos 2 mensajes para generar un informe"


def _parse_document_id(raw_id) -> uuid.UUID | None:
    """Convierte el document_id guardado en source_chunks (string en JSON) de vuelta a UUID."""
    if raw_id is None:
        return None
    return raw_id if isinstance(raw_id, uuid.UUID) else uuid.UUID(str(raw_id))


async def _enrich_source_chunks_with_document_names(db: AsyncSession, messages: list[Message]) -> None:
    """Agrega 'document_name' a cada source_chunk en memoria (solo para el render del PDF,
    nunca se persiste: no se llama a db.commit() en este flujo de solo lectura)."""
    document_ids = {
        _parse_document_id(source.get("document_id"))
        for msg in messages
        for source in (msg.source_chunks or [])
        if source.get("document_id")
    }
    document_ids.discard(None)

    filenames = await _get_document_filenames(db, document_ids)

    for msg in messages:
        if msg.source_chunks:
            msg.source_chunks = [
                {
                    **source,
                    "document_name": filenames.get(_parse_document_id(source.get("document_id")), "Documento"),
                }
                for source in msg.source_chunks
            ]


@router.post("/conversations/{conversation_id}")
async def generate_conversation_report(
    conversation_id: uuid.UUID,
    payload: ReportRequest,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
):
    """Genera un informe PDF de cumplimiento normativo a partir del historial de una
    conversacion (o el rango de fechas indicado) y lo retorna para descarga directa.

    Mismo criterio de acceso que ver los mensajes de la conversacion: el dueno, o un admin del
    tenant (rol de auditor, ver _get_viewable_conversation_or_404) -- antes este endpoint solo
    validaba el tenant, asi que cualquier usuario del tenant podia generar el informe de una
    conversacion ajena que ni siquiera podia leer en el chat.
    """
    conversation = await _get_viewable_conversation_or_404(db, conversation_id, tenant.id, current_user)

    result = await db.execute(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at.asc())
    )
    all_messages = list(result.scalars().all())

    if len(all_messages) < MIN_MESSAGES_FOR_REPORT:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=TOO_FEW_MESSAGES_DETAIL)

    date_from = payload.date_from or all_messages[0].created_at.date()
    date_to = payload.date_to or all_messages[-1].created_at.date()

    messages = [msg for msg in all_messages if date_from <= msg.created_at.date() <= date_to]

    if len(messages) < MIN_MESSAGES_FOR_REPORT:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=TOO_FEW_MESSAGES_DETAIL)

    await _enrich_source_chunks_with_document_names(db, messages)

    summary = await report_service.generate_compliance_summary(messages, tenant.name)
    pdf_bytes = await report_service.build_pdf(conversation, messages, summary, tenant.name, date_from, date_to)

    filename = f"informe_{str(conversation_id)[:8]}_{date_to.isoformat()}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
