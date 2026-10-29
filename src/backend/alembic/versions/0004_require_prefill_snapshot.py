"""Require discovery prefill provenance.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "discovery_sessions", "prefill_snapshot", existing_type=postgresql.JSONB(), nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "discovery_sessions", "prefill_snapshot", existing_type=postgresql.JSONB(), nullable=True,
    )
