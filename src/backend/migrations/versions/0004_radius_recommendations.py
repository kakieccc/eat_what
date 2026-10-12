"""Store search radius preferences and retire workflow v4 in-flight tasks."""

import sqlalchemy as sa
from alembic import op

revision = "0004_radius_recommendations"
down_revision = "0003_simplify_workflow_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "preferences",
        sa.Column("typical_radius_meters", sa.Integer(), nullable=False, server_default="2000"),
    )
    op.alter_column("preferences", "typical_radius_meters", server_default=None)
    op.alter_column(
        "discovery_sessions", "max_walking_minutes", existing_type=sa.Integer(), nullable=True
    )
    op.execute("""
        UPDATE tasks SET status = 'failed', phase = 'failed',
            error_code = 'WORKFLOW_UPGRADED',
            error_message = '推荐范围规则已更新，请重新推荐',
            lease_token = NULL, lease_until = NULL, completed_at = now()
        WHERE status IN ('queued', 'running', 'waiting_confirmation')
            AND state->>'schema_version' IS DISTINCT FROM '5'
    """)
    op.execute("""
        UPDATE decision_runs SET status = 'failed', error_code = 'WORKFLOW_UPGRADED',
            completed_at = now()
        WHERE status IN ('pending', 'running', 'awaitingConfirmation')
            AND workflow_version <> '5'
    """)
    op.execute("""
        UPDATE decision_confirmations SET status = 'rejected', resolved_at = now()
        WHERE status = 'pending' AND decision_run_id IN (
            SELECT id FROM decision_runs
            WHERE error_code = 'WORKFLOW_UPGRADED' AND workflow_version <> '5'
        )
    """)
    op.execute("""
        UPDATE task_steps SET status = 'failed', error_code = 'WORKFLOW_UPGRADED',
            error_message = '推荐范围规则已更新', completed_at = now()
        WHERE status = 'running' AND task_id IN (
            SELECT id FROM tasks WHERE error_code = 'WORKFLOW_UPGRADED'
        )
    """)


def downgrade() -> None:
    # Restore the previous default walking limit for records created by workflow v5.
    op.execute(
        "UPDATE discovery_sessions SET max_walking_minutes = 15 WHERE max_walking_minutes IS NULL"
    )
    op.alter_column(
        "discovery_sessions", "max_walking_minutes", existing_type=sa.Integer(), nullable=False
    )
    op.drop_column("preferences", "typical_radius_meters")
