"""Initial release schema.

Revision ID: 0001
Revises: None
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_rate_limits",
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash"),
    )
    op.create_index(
        "ix_auth_rate_limits_window_started_at", "auth_rate_limits", ["window_started_at"]
    )
    op.create_table(
        "place_cache",
        sa.Column("cache_key", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cache_key"),
    )
    op.create_index(op.f("ix_place_cache_expires_at"), "place_cache", ["expires_at"], unique=False)
    op.create_table(
        "users",
        sa.Column("username", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=40), nullable=False),
        sa.Column("password", sa.String(length=255), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_auth_sessions_user_id"), "auth_sessions", ["user_id"], unique=False)
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    op.create_table(
        "discovery_sessions",
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("current_run_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("seen_place_keys", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("request_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("prefill_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_discovery_sessions_user_id"), "discovery_sessions", ["user_id"], unique=False
    )
    op.create_table(
        "idempotency_records",
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("endpoint", sa.String(length=160), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("request_hash", sa.String(length=128), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "endpoint", "idempotency_key"),
    )
    op.create_index(
        op.f("ix_idempotency_records_user_id"), "idempotency_records", ["user_id"], unique=False
    )
    op.create_index("ix_idempotency_records_expires_at", "idempotency_records", ["expires_at"])
    op.create_table(
        "preferences",
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("learned", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("overrides", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("meal_count", sa.Integer(), nullable=False),
        sa.Column("requested_count", sa.Integer(), nullable=False),
        sa.Column("attempted_count", sa.Integer(), nullable=False),
        sa.Column("claimed_count", sa.Integer(), nullable=False),
        sa.Column("learning_status", sa.String(length=16), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_token", sa.String(length=36), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(
        "preference_learning_queue", "preferences", ["learning_status", "lease_until"], unique=False
    )
    op.create_table(
        "decision_runs",
        sa.Column("discovery_session_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("parent_decision_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("workflow_version", sa.String(length=32), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("refinement_action", sa.String(length=64), nullable=False),
        sa.Column("original_request", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("effective_preferences", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("filter_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("excluded_place_keys", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model_provider", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("llm_used", sa.Boolean(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["discovery_session_id"],
            ["discovery_sessions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["parent_decision_id"],
            ["decision_runs.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_decision_runs_discovery_session_id"),
        "decision_runs",
        ["discovery_session_id"],
        unique=False,
    )
    op.create_index(op.f("ix_decision_runs_status"), "decision_runs", ["status"], unique=False)
    op.create_table(
        "place_candidates",
        sa.Column("decision_run_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("place_key", sa.String(length=128), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("place_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["decision_run_id"],
            ["decision_runs.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("decision_run_id", "place_key"),
        sa.UniqueConstraint("decision_run_id", "rank"),
    )
    op.create_index(
        op.f("ix_place_candidates_decision_run_id"),
        "place_candidates",
        ["decision_run_id"],
        unique=False,
    )
    op.create_table(
        "tasks",
        sa.Column("decision_run_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("parent_task_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("phase", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.String(length=64), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["decision_run_id"],
            ["decision_runs.id"],
        ),
        sa.ForeignKeyConstraint(
            ["parent_task_id"],
            ["tasks.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tasks_decision_run_id"), "tasks", ["decision_run_id"], unique=False)
    op.create_index(op.f("ix_tasks_status"), "tasks", ["status"], unique=False)
    op.create_index("task_claim_status_lease", "tasks", ["status", "lease_until"], unique=False)
    op.create_index("task_run_created", "tasks", ["decision_run_id", "created_at"], unique=False)
    op.create_table(
        "place_choices",
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("discovery_session_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("place_candidate_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["discovery_session_id"],
            ["discovery_sessions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["place_candidate_id"],
            ["place_candidates.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("discovery_session_id"),
    )
    op.create_index(op.f("ix_place_choices_user_id"), "place_choices", ["user_id"], unique=False)
    op.create_table(
        "task_events",
        sa.Column("task_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "sequence"),
    )
    op.create_index("task_event_order", "task_events", ["task_id", "sequence"], unique=False)
    op.create_table(
        "task_steps",
        sa.Column("task_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "key"),
        sa.UniqueConstraint("task_id", "ordinal"),
    )
    op.create_index("task_step_status", "task_steps", ["task_id", "status"], unique=False)
    op.create_table(
        "preference_samples",
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("discovery_session_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("choice_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("meal_number", sa.Integer(), nullable=False),
        sa.Column("prefill_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("active_changes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("final_conditions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("request_text", sa.Text(), nullable=False),
        sa.Column("restaurant_facts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["choice_id"],
            ["place_choices.id"],
        ),
        sa.ForeignKeyConstraint(
            ["discovery_session_id"],
            ["discovery_sessions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("choice_id"),
        sa.UniqueConstraint("discovery_session_id"),
        sa.UniqueConstraint("user_id", "meal_number"),
    )
    op.create_foreign_key(
        "fk_discovery_current_run",
        "discovery_sessions",
        "decision_runs",
        ["current_run_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_discovery_current_run", "discovery_sessions", type_="foreignkey")
    op.drop_table("preference_samples")
    op.drop_index("task_step_status", table_name="task_steps")
    op.drop_table("task_steps")
    op.drop_index("task_event_order", table_name="task_events")
    op.drop_table("task_events")
    op.drop_index(op.f("ix_place_choices_user_id"), table_name="place_choices")
    op.drop_table("place_choices")
    op.drop_index("task_run_created", table_name="tasks")
    op.drop_index("task_claim_status_lease", table_name="tasks")
    op.drop_index(op.f("ix_tasks_status"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_decision_run_id"), table_name="tasks")
    op.drop_table("tasks")
    op.drop_index(op.f("ix_place_candidates_decision_run_id"), table_name="place_candidates")
    op.drop_table("place_candidates")
    op.drop_index(op.f("ix_decision_runs_status"), table_name="decision_runs")
    op.drop_index(op.f("ix_decision_runs_discovery_session_id"), table_name="decision_runs")
    op.drop_table("decision_runs")
    op.drop_index("preference_learning_queue", table_name="preferences")
    op.drop_table("preferences")
    op.drop_index("ix_idempotency_records_expires_at", table_name="idempotency_records")
    op.drop_index(op.f("ix_idempotency_records_user_id"), table_name="idempotency_records")
    op.drop_table("idempotency_records")
    op.drop_index(op.f("ix_discovery_sessions_user_id"), table_name="discovery_sessions")
    op.drop_table("discovery_sessions")
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_index(op.f("ix_auth_sessions_user_id"), table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_table("users")
    op.drop_index(op.f("ix_place_cache_expires_at"), table_name="place_cache")
    op.drop_table("place_cache")
    op.drop_index("ix_auth_rate_limits_window_started_at", table_name="auth_rate_limits")
    op.drop_table("auth_rate_limits")
