"""baseline snapshot

Revision ID: 20260409_0001
Revises:
Create Date: 2026-04-09 09:00:00.000000
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260409_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Baseline snapshot migration.

    当前仓库历史上大量结构由 SQLAlchemy create_all 与非生产 schema patch 演进而来。
    该 revision 用于建立正式 Alembic 治理入口，后续结构变更必须通过新 revision 管理。
    本基线不执行 destructive DDL，作为现网快照锚点。
    """
    pass


def downgrade() -> None:
    """Baseline revision 不执行回滚 DDL。"""
    pass
