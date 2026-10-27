"""tabla external_norms: estado del sincronizador automatico de normativa (Minambiente)

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    external_norm_source_enum = postgresql.ENUM("minambiente", name="external_norm_source")
    external_norm_status_enum = postgresql.ENUM("pending", "ingested", "failed", name="external_norm_status")
    external_norm_source_enum.create(bind, checkfirst=True)
    external_norm_status_enum.create(bind, checkfirst=True)
    external_norm_source_enum.create_type = False
    external_norm_status_enum.create_type = False

    op.create_table(
        "external_norms",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("source", external_norm_source_enum, nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("pdf_url", sa.String(length=1000), nullable=False, unique=True),
        sa.Column("published_at", sa.Date(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", external_norm_status_enum, nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("supersedes_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("external_norms")
    bind = op.get_bind()
    postgresql.ENUM(name="external_norm_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="external_norm_source").drop(bind, checkfirst=True)
