"""Keep one current recommendation per discovery session.

Stop old API/workers before applying this data migration. Discarded results cannot
be recovered by downgrade.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("discovery_sessions", sa.Column("current_run_id", sa.Uuid(as_uuid=False), nullable=True))
    op.add_column("discovery_sessions", sa.Column(
        "seen_place_keys", postgresql.JSONB(), nullable=False, server_default="[]",
    ))
    op.create_foreign_key(
        "fk_discovery_current_run", "discovery_sessions", "decision_runs",
        ["current_run_id"], ["id"], ondelete="SET NULL",
    )
    op.alter_column("place_candidates", "reason", type_=sa.Text(), existing_type=sa.String(600))
    op.execute("""
        UPDATE discovery_sessions s SET current_run_id = (
            SELECT r.id FROM decision_runs r WHERE r.discovery_session_id = s.id
            ORDER BY r.created_at DESC, r.id DESC LIMIT 1
        )
    """)
    op.execute("""
        UPDATE discovery_sessions s SET seen_place_keys = COALESCE((
            SELECT jsonb_agg(DISTINCT c.place_key) FROM place_candidates c
            JOIN decision_runs r ON r.id = c.decision_run_id
            WHERE r.discovery_session_id = s.id
        ), '[]'::jsonb)
    """)
    op.execute("""
        UPDATE idempotency_records i SET response_body = '{"superseded": true}'::jsonb
        WHERE endpoint = 'place-choices' AND response_body->>'candidateId' IN (
            SELECT c.id::text FROM place_candidates c JOIN decision_runs r ON r.id = c.decision_run_id
            JOIN discovery_sessions s ON s.id = r.discovery_session_id
            WHERE r.id <> s.current_run_id
        )
    """)
    op.execute("""
        DELETE FROM place_choices WHERE place_candidate_id IN (
            SELECT c.id FROM place_candidates c JOIN decision_runs r ON r.id = c.decision_run_id
            JOIN discovery_sessions s ON s.id = r.discovery_session_id
            WHERE r.id <> s.current_run_id
        )
    """)
    op.execute("""
        DELETE FROM place_candidates WHERE decision_run_id IN (
            SELECT r.id FROM decision_runs r JOIN discovery_sessions s ON s.id = r.discovery_session_id
            WHERE r.id <> s.current_run_id
        )
    """)
    op.execute("""
        UPDATE tasks t SET status = 'superseded', state = '{}'::jsonb,
            lease_token = NULL, lease_until = NULL, error_message = NULL
        FROM decision_runs r, discovery_sessions s
        WHERE t.decision_run_id = r.id AND s.id = r.discovery_session_id AND r.id <> s.current_run_id
    """)
    op.execute("DELETE FROM task_events WHERE task_id IN (SELECT id FROM tasks WHERE status = 'superseded')")
    op.execute("""
        UPDATE decision_runs r SET original_request = '{}'::jsonb, intent = '{}'::jsonb,
            effective_preferences = '{}'::jsonb, filter_summary = '{}'::jsonb,
            excluded_place_keys = '[]'::jsonb
        FROM discovery_sessions s WHERE s.id = r.discovery_session_id AND r.id <> s.current_run_id
    """)
    # Old checkpoints cannot bypass the new semantic gate by resuming after reranking.
    op.execute("""
        UPDATE tasks t SET status = 'failed', error_code = 'WORKFLOW_VERSION_CHANGED',
            lease_token = NULL, lease_until = NULL,
            state = jsonb_build_object(
                'excluded', COALESCE(state->'excluded', '[]'::jsonb),
                'old_cuisines', COALESCE(state->'old_cuisines', '[]'::jsonb),
                'action', COALESCE(state->'action', '\"\"'::jsonb)
            )
        WHERE status IN ('queued', 'running')
    """)
    op.execute("""
        UPDATE decision_runs SET status = 'failed', error_code = 'WORKFLOW_VERSION_CHANGED'
        WHERE status IN ('pending', 'running')
    """)
    op.alter_column("discovery_sessions", "seen_place_keys", server_default=None)


def downgrade() -> None:
    op.drop_constraint("fk_discovery_current_run", "discovery_sessions", type_="foreignkey")
    op.drop_column("discovery_sessions", "current_run_id")
    op.drop_column("discovery_sessions", "seen_place_keys")
    # Existing reasons may exceed the previous limit. Keep their content intact.
