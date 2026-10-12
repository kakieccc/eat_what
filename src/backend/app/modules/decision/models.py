from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
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

    origin_latitude: Mapped[float] = mapped_column(nullable=False)
    origin_longitude: Mapped[float] = mapped_column(nullable=False)
    origin_address: Mapped[str] = mapped_column(String(200), default="")
    budget_per_person_min: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    budget_per_person_max: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    radius_meters: Mapped[int] = mapped_column(Integer, nullable=False)
    preferred_cuisines: Mapped[list[str]] = mapped_column(JSONB, default=list)
    excluded_cuisines: Mapped[list[str]] = mapped_column(JSONB, default=list)
    desired_tags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    meal_period: Mapped[str] = mapped_column(String(32), nullable=False)
    party_size: Mapped[int] = mapped_column(Integer, nullable=False)
    open_now_preferred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    request_text: Mapped[str] = mapped_column(String(300), default="")
    normalized_preferences: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)


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


class DecisionConfirmation(IdentityMixin, Base):
    __tablename__ = "decision_confirmations"

    decision_run_id: Mapped[str] = mapped_column(
        ForeignKey("decision_runs.id"), unique=True, nullable=False
    )
    changes: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlaceCandidate(IdentityMixin, Base):
    __tablename__ = "place_candidates"

    decision_run_id: Mapped[str] = mapped_column(
        ForeignKey("decision_runs.id"), nullable=False, index=True
    )
    place_key: Mapped[str] = mapped_column(String(128), nullable=False)
    external_place_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    category_code: Mapped[str] = mapped_column(String(64), default="")
    category_name: Mapped[str] = mapped_column(String(200), default="")
    cuisine_types: Mapped[list[str]] = mapped_column(JSONB, default=list)
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    address: Mapped[str] = mapped_column(String(250), default="")
    latitude: Mapped[float] = mapped_column(nullable=False)
    longitude: Mapped[float] = mapped_column(nullable=False)
    straight_line_distance_meters: Mapped[int] = mapped_column(Integer, nullable=False)
    rating: Mapped[float | None]
    average_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    business_status: Mapped[str] = mapped_column(String(16), default="unknown")
    opening_hours_text: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(80))
    photos: Mapped[list[str]] = mapped_column(JSONB, default=list)
    score: Mapped[float] = mapped_column(default=0)
    score_breakdown: Mapped[dict[str, float]] = mapped_column(JSONB, default=dict)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(600), default="")
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list)
    navigation_url: Mapped[str | None] = mapped_column(String(1000))
    place_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("decision_run_id", "rank"),
        UniqueConstraint("decision_run_id", "place_key"),
        Index("candidate_run_score", "decision_run_id", "score"),
    )


class IdempotencyRecord(IdentityMixin, Base):
    __tablename__ = "idempotency_records"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    endpoint: Mapped[str] = mapped_column(String(160), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, default=200)
    response_body: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("user_id", "endpoint", "idempotency_key"),)
