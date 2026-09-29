from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.models.base import Base, IdentityMixin


class TaskKind(StrEnum):
    decision = "decision"
    refinement = "refinement"
    resume = "resume"


class TaskStatus(StrEnum):
    queued = "queued"
    running = "running"
    waiting_confirmation = "waiting_confirmation"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"
    superseded = "superseded"


class Task(IdentityMixin, Base):
    __tablename__ = "tasks"

    decision_run_id: Mapped[str] = mapped_column(
        ForeignKey("decision_runs.id"), nullable=False, index=True
    )
    parent_task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"))
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default=TaskKind.decision.value)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=TaskStatus.queued.value, index=True
    )
    phase: Mapped[str] = mapped_column(String(64), nullable=False, default="queued")
    request_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    state: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    result_refs: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(64))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(500))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("task_claim_status_lease", "status", "lease_until"),
        Index("task_run_created", "decision_run_id", "created_at"),
    )


class TaskStep(IdentityMixin, Base):
    __tablename__ = "task_steps"

    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_state: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    output_state: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(500))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("task_id", "key"),
        UniqueConstraint("task_id", "ordinal"),
        Index("task_step_status", "task_id", "status"),
    )


class TaskEvent(IdentityMixin, Base):
    __tablename__ = "task_events"

    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("task_id", "sequence"),
        Index("task_event_order", "task_id", "sequence"),
    )
