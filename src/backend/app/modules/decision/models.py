from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, IdentityMixin
from app.modules.decision.workflow.state import PROMPT_VERSION, SCHEMA_VERSION


class DiscoverySession(IdentityMixin, Base):
    __tablename__ = "discovery_sessions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    current_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("decision_runs.id", name="fk_discovery_current_run", use_alter=True, ondelete="SET NULL")
    )
    seen_place_keys: Mapped[list[str]] = mapped_column(JSONB, default=list)

    request_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    prefill_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class DecisionRun(IdentityMixin, Base):
    __tablename__ = "decision_runs"

    discovery_session_id: Mapped[str] = mapped_column(
        ForeignKey("discovery_sessions.id"), nullable=False, index=True
    )
    parent_decision_id: Mapped[str | None] = mapped_column(ForeignKey("decision_runs.id"))
    workflow_version: Mapped[str] = mapped_column(String(32), default=str(SCHEMA_VERSION))
    prompt_version: Mapped[str] = mapped_column(String(32), default=PROMPT_VERSION)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    refinement_action: Mapped[str] = mapped_column(String(64), default="")
    original_request: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    effective_preferences: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    filter_summary: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)
    excluded_place_keys: Mapped[list[str]] = mapped_column(JSONB, default=list)
    provider: Mapped[str] = mapped_column(String(32), default="amap")
    model_provider: Mapped[str] = mapped_column(String(64), default="openai-compatible")
    model_name: Mapped[str] = mapped_column(String(128), default="")
    llm_used: Mapped[bool] = mapped_column(Boolean, default=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlaceCandidate(IdentityMixin, Base):
    __tablename__ = "place_candidates"

    decision_run_id: Mapped[str] = mapped_column(
        ForeignKey("decision_runs.id"), nullable=False, index=True
    )
    place_key: Mapped[str] = mapped_column(String(128), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    place_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("decision_run_id", "rank"),
        UniqueConstraint("decision_run_id", "place_key"),
    )


class IdempotencyRecord(IdentityMixin, Base):
    __tablename__ = "idempotency_records"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    endpoint: Mapped[str] = mapped_column(String(160), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, default=200)
    response_body: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    __table_args__ = (UniqueConstraint("user_id", "endpoint", "idempotency_key"),)
