"""crea el usuario administrador del tenant base (_base)

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-19
"""

from __future__ import annotations

import os

import bcrypt
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

BASE_TENANT_ID = "00000000-0000-0000-0000-000000000001"
BASE_ADMIN_USER_ID = "00000000-0000-0000-0000-000000000002"


def upgrade() -> None:
    admin_email = os.environ.get("BASE_ADMIN_EMAIL", "admin@base.ecolex.internal")
    password = os.environ.get("BASE_ADMIN_PASSWORD", "changeme_en_produccion")
    hashed_password = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()

    op.execute(
        sa.text(
            """
            INSERT INTO users (
                id, tenant_id, email, hashed_password, role, is_active, created_at, updated_at
            ) VALUES (
                CAST(:id AS uuid), CAST(:tenant_id AS uuid), :email, :hashed_password, 'admin', true, NOW(), NOW()
            ) ON CONFLICT (id) DO NOTHING
            """
        ).bindparams(
            id=BASE_ADMIN_USER_ID,
            tenant_id=BASE_TENANT_ID,
            email=admin_email,
            hashed_password=hashed_password,
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM users WHERE id = CAST(:id AS uuid)").bindparams(id=BASE_ADMIN_USER_ID))
