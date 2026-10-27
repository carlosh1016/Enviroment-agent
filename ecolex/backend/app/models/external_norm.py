import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import GUID, Base


class ExternalNormSource(str, enum.Enum):
    """Fuente externa de la que se descubrio una norma via sincronizacion automatica."""

    MINAMBIENTE = "minambiente"


class ExternalNormStatus(str, enum.Enum):
    """Estado del intento de ingesta de una norma descubierta por el sincronizador."""

    PENDING = "pending"
    INGESTED = "ingested"
    FAILED = "failed"


class ExternalNorm(Base):
    """Registro de una norma descubierta por el sincronizador automatico de una fuente externa
    (hoy solo Minambiente). Sirve dos propositos: (1) no volver a descargar/ingestar la misma
    norma en cada corrida (dedupe por pdf_url), y (2) guardar una advertencia simple cuando el
    titulo de una norma nueva sugiere que deroga/modifica una ya ingestada, para revision manual
    (ver minambiente_sync_service.detect_supersession -- nunca reemplaza contenido automaticamente)."""

    __tablename__ = "external_norms"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    source: Mapped[ExternalNormSource] = mapped_column(
        Enum(
            ExternalNormSource,
            name="external_norm_source",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    pdf_url: Mapped[str] = mapped_column(String(1000), nullable=False, unique=True)
    published_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[ExternalNormStatus] = mapped_column(
        Enum(
            ExternalNormStatus,
            name="external_norm_status",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=ExternalNormStatus.PENDING,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    supersedes_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
