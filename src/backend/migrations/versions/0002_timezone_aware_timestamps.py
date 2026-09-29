"""Store decision and idempotency timestamps with time zones."""

from alembic import op
from sqlalchemy import DateTime

revision = "0002_timezone_aware_timestamps"
down_revision = "0001_user_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table, column in (
        ("idempotency_records", "expires_at"),
        ("decision_runs", "completed_at"),
        ("decision_confirmations", "resolved_at"),
    ):
        op.alter_column(
            table,
            column,
            existing_type=DateTime(timezone=False),
            type_=DateTime(timezone=True),
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )


def downgrade() -> None:
    for table, column in (
        ("decision_confirmations", "resolved_at"),
        ("decision_runs", "completed_at"),
        ("idempotency_records", "expires_at"),
    ):
        op.alter_column(
            table,
            column,
            existing_type=DateTime(timezone=True),
            type_=DateTime(timezone=False),
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )
