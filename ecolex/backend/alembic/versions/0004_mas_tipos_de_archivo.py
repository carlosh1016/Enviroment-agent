"""agrega mhtml, html, xlsx y csv a document_file_type

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-19
"""

from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

NEW_VALUES = ["mhtml", "html", "xlsx", "csv"]


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE no puede ejecutarse y luego USARSE dentro de la misma
    # transaccion en PostgreSQL, pero aqui solo se agrega el valor (se usa en requests futuros,
    # nunca en esta misma migracion), asi que correrlo dentro de la transaccion normal de
    # Alembic es seguro.
    for value in NEW_VALUES:
        op.execute(f"ALTER TYPE document_file_type ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # PostgreSQL no soporta DROP VALUE en un tipo enum (requeriria recrear el tipo completo y
    # migrar todas las columnas que lo usan). Dado que esta migracion solo agrega opciones y
    # nunca las usa por si misma, un downgrade no-op es seguro: deja los valores nuevos
    # declarados pero sin filas que los usen, a menos que ya se hayan subido documentos de esos
    # tipos (en cuyo caso no hay downgrade seguro posible sin perder esos documentos).
    pass
