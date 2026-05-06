"""add paas erp system type

Revision ID: 20260410_0002
Revises: 20260409_0001
Create Date: 2026-04-10 08:10:00.000000
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260410_0002"
down_revision = "20260409_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE erpsystemtype ADD VALUE IF NOT EXISTS 'PAAS'")


def downgrade() -> None:
    # PostgreSQL enum value downgrade is intentionally no-op.
    pass
