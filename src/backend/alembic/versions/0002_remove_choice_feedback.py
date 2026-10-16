"""Remove choice feedback.

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
    op.drop_column("place_choices", "feedback")


def downgrade() -> None:
    op.add_column(
        "place_choices",
        sa.Column("feedback", sa.String(length=300), nullable=False, server_default=""),
    )
    op.alter_column("place_choices", "feedback", server_default=None)
