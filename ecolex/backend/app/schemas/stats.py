import uuid
from datetime import date

from pydantic import BaseModel


class DayActivity(BaseModel):
    """Conversaciones y mensajes creados en un dia especifico (ver ACTIVITY_WINDOW_DAYS)."""

    date: date
    conversations: int
    messages: int


class CitedDocument(BaseModel):
    """Un documento y cuantas veces aparecio como fuente en respuestas del asistente."""

    document_id: uuid.UUID
    document_name: str
    citations: int


class DashboardStats(BaseModel):
    """Agregados para las graficas del dashboard (GET /api/v1/stats/dashboard)."""

    documents_by_status: dict[str, int]
    documents_by_type: dict[str, int]
    activity_last_14_days: list[DayActivity]
    top_cited_documents: list[CitedDocument]
