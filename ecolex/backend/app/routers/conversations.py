import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_tenant, get_current_user
from app.logging_config import get_logger
from app.models.conversation import Conversation, Message, MessageRole
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas import success_response
from app.schemas.conversation import (
    ConversationCreate,
    ConversationRead,
    ConversationUpdate,
    MessageCreate,
    MessageRead,
    PaginatedConversations,
)
from app.services import rag_service

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])
logger = get_logger(__name__)


async def _get_own_conversation_or_404(
    db: AsyncSession, conversation_id: uuid.UUID, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> Conversation:
    """Obtiene una conversacion validando tenant (404) y propiedad del usuario autenticado (403)."""
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.tenant_id == tenant_id)
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversacion no encontrada")
    if conversation.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tiene acceso a esta conversacion")
    return conversation


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreate,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
):
    """Crea una nueva conversacion para el usuario actual."""
    conversation = Conversation(tenant_id=tenant.id, user_id=current_user.id, title=payload.title)
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)

    return success_response(
        data=ConversationRead.model_validate(conversation).model_dump(mode="json"),
        message="Conversacion creada exitosamente",
    )


@router.get("/")
async def list_conversations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
):
    """Lista las conversaciones del usuario autenticado (no las de otros usuarios del mismo tenant)."""
    base_query = select(Conversation).where(
        Conversation.tenant_id == tenant.id, Conversation.user_id == current_user.id
    )

    count_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = count_result.scalar_one()

    result = await db.execute(
        base_query.order_by(Conversation.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    conversations = result.scalars().all()

    data = PaginatedConversations(
        items=[ConversationRead.model_validate(c) for c in conversations],
        total=total,
        page=page,
        page_size=page_size,
    )
    return success_response(data=data.model_dump(mode="json"), message="Conversaciones obtenidas exitosamente")


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: uuid.UUID,
    payload: MessageCreate,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
):
    """Envia un mensaje del usuario al agente RAG y retorna la respuesta generada con sus fuentes.

    El mensaje del usuario se guarda antes de llamar al RAG, de modo que no se pierde si este falla.
    """
    await _get_own_conversation_or_404(db, conversation_id, tenant.id, current_user.id)

    user_message = Message(
        tenant_id=tenant.id, conversation_id=conversation_id, role=MessageRole.USER, content=payload.content
    )
    db.add(user_message)
    await db.commit()
    await db.refresh(user_message)

    try:
        assistant_message = await rag_service.chat(
            db, conversation_id, payload.content, tenant.id, user_message_id=user_message.id
        )
    except Exception as exc:
        await db.rollback()
        logger.error("Error generando la respuesta del agente: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El asistente no pudo responder. Tu pregunta fue guardada, puedes intentar de nuevo.",
        ) from exc

    return success_response(
        data=MessageRead.model_validate(assistant_message).model_dump(mode="json"),
        message="Respuesta generada exitosamente",
    )


@router.get("/{conversation_id}/messages")
async def get_messages(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
):
    """Retorna el historial completo de una conversacion en orden cronologico."""
    await _get_own_conversation_or_404(db, conversation_id, tenant.id, current_user.id)

    result = await db.execute(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at.asc())
    )
    messages = result.scalars().all()

    return success_response(
        data=[MessageRead.model_validate(m).model_dump(mode="json") for m in messages],
        message="Historial obtenido exitosamente",
    )


@router.patch("/{conversation_id}")
async def update_conversation(
    conversation_id: uuid.UUID,
    payload: ConversationUpdate,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
):
    """Actualiza el titulo de una conversacion. Solo su dueno puede hacerlo."""
    conversation = await _get_own_conversation_or_404(db, conversation_id, tenant.id, current_user.id)
    conversation.title = payload.title
    await db.commit()
    await db.refresh(conversation)

    return success_response(
        data=ConversationRead.model_validate(conversation).model_dump(mode="json"),
        message="Conversacion actualizada exitosamente",
    )


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
):
    """Elimina una conversacion y todos sus mensajes (CASCADE)."""
    conversation = await _get_own_conversation_or_404(db, conversation_id, tenant.id, current_user.id)
    await db.delete(conversation)
    await db.commit()

    return success_response(data=None, message="Conversacion eliminada exitosamente")
