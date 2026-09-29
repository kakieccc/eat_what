"""Keep one task snapshot and retire workflow v3 in-flight tasks."""

from alembic import op

revision = "0003_simplify_workflow_state"
down_revision = "0002_timezone_aware_timestamps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE tasks SET status = 'failed', phase = 'failed',
            error_code = 'WORKFLOW_UPGRADED',
            error_message = '任务版本已更新，请重新推荐',
            lease_token = NULL, lease_until = NULL, completed_at = now()
        WHERE status IN ('queued', 'running', 'waiting_confirmation')
    """)
    op.execute("""
        UPDATE decision_runs SET status = 'failed', error_code = 'WORKFLOW_UPGRADED',
            completed_at = now()
        WHERE status IN ('pending', 'running', 'awaitingConfirmation')
    """)
    op.execute("""
        UPDATE decision_confirmations SET status = 'rejected', resolved_at = now()
        WHERE status = 'pending'
    """)
    op.execute("""
        UPDATE task_steps SET status = 'failed', error_code = 'WORKFLOW_UPGRADED',
            error_message = '任务版本已更新', completed_at = now()
        WHERE status = 'running'
    """)
    op.drop_column("task_steps", "input_state")
    op.drop_column("task_steps", "output_state")
    op.drop_column("tasks", "result_refs")


def downgrade() -> None:
    op.execute("ALTER TABLE tasks ADD COLUMN result_refs JSONB NOT NULL DEFAULT '[]'::jsonb")
    op.execute("ALTER TABLE task_steps ADD COLUMN input_state JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE task_steps ADD COLUMN output_state JSONB NOT NULL DEFAULT '{}'::jsonb")
