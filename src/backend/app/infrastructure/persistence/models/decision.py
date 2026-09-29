from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.models.base import Base, IdentityMixin


class DecisionRun(IdentityMixin, Base):
    __tablename__ = "decision_runs"

    discovery_session_id: Mapped[str] = mapped_column(
        ForeignKey("discovery_sessions.id"), nullable=False, index=True
    )
    parent_decision_id: Mapped[str | None] = mapped_column(ForeignKey("decision_runs.id"))
    workflow_version: Mapped[str] = mapped_column(String(32), default="3")
    prompt_version: Mapped[str] = mapped_column(String(32), default="1")
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
