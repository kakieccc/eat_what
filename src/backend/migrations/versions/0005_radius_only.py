"""Remove retired route data and advance radius-only workflow state."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_radius_only"
down_revision = "0004_radius_recommendations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("route_cache")
    op.drop_column("preferences", "typical_max_walking_minutes")
    op.drop_column("discovery_sessions", "max_walking_minutes")
    op.drop_column("place_candidates", "walking_distance_meters")
    op.drop_column("place_candidates", "walking_duration_seconds")
    op.drop_column("place_candidates", "route_snapshot")
    op.execute("""
        UPDATE tasks SET status = 'failed', phase = 'failed',
            error_code = 'WORKFLOW_UPGRADED',
            error_message = '推荐数据结构已更新，请重新推荐',
            lease_token = NULL, lease_until = NULL, completed_at = now()
        WHERE status IN ('queued', 'running', 'waiting_confirmation')
            AND state->>'schema_version' IS DISTINCT FROM '6'
    """)
    op.execute("""
        UPDATE decision_runs SET status = 'failed', error_code = 'WORKFLOW_UPGRADED',
            completed_at = now()
        WHERE status IN ('pending', 'running', 'awaitingConfirmation')
            AND workflow_version <> '6'
    """)
    op.execute("""
        UPDATE decision_confirmations SET status = 'rejected', resolved_at = now()
        WHERE status = 'pending' AND decision_run_id IN (
            SELECT id FROM decision_runs
            WHERE error_code = 'WORKFLOW_UPGRADED' AND workflow_version <> '6'
        )
    """)
    op.execute("""
        UPDATE task_steps SET status = 'failed', error_code = 'WORKFLOW_UPGRADED',
            error_message = '推荐数据结构已更新', completed_at = now()
        WHERE status = 'running' AND task_id IN (
            SELECT id FROM tasks WHERE error_code = 'WORKFLOW_UPGRADED'
        )
    """)


def downgrade() -> None:
    op.add_column("place_candidates", sa.Column("route_snapshot", postgresql.JSONB()))
    op.add_column("place_candidates", sa.Column("walking_duration_seconds", sa.Integer()))
    op.add_column("place_candidates", sa.Column("walking_distance_meters", sa.Integer()))
    op.add_column("discovery_sessions", sa.Column("max_walking_minutes", sa.Integer()))
    op.add_column("preferences", sa.Column("typical_max_walking_minutes", sa.Integer()))
    op.create_table(
        "route_cache",
        sa.Column("cache_key", sa.String(128), nullable=False),
        sa.Column("origin_geohash", sa.String(32), nullable=False),
        sa.Column("destination_place_id", sa.String(128), nullable=False),
        sa.Column("travel_mode", sa.String(32), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cache_key"),
    )
    op.create_index("ix_route_cache_expires_at", "route_cache", ["expires_at"])
