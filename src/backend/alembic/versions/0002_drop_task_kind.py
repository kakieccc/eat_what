"""Remove the unused task kind.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("tasks", "kind")


def downgrade() -> None:
    op.add_column("tasks", sa.Column("kind", sa.String(length=32), nullable=True))
    op.execute("""
        UPDATE tasks
        SET kind = CASE WHEN decision_runs.parent_decision_id IS NULL
            THEN 'decision' ELSE 'refinement' END
        FROM decision_runs
        WHERE decision_runs.id = tasks.decision_run_id
    """)
    op.alter_column("tasks", "kind", nullable=False)
