"""Require opt-in for preference learning.

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
    op.add_column("preferences", sa.Column(
        "learning_enabled", sa.Boolean(), nullable=False, server_default=sa.false(),
    ))
    op.execute("""
        UPDATE preferences
        SET learning_status = 'idle', requested_count = attempted_count,
            lease_token = NULL, lease_until = NULL
    """)
    op.alter_column("preferences", "learning_enabled", server_default=None)


def downgrade() -> None:
    op.drop_column("preferences", "learning_enabled")
