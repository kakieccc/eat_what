from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, IdentityMixin


class Preference(IdentityMixin, Base):
    __tablename__ = "preferences"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    learned: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    overrides: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    meal_count: Mapped[int] = mapped_column(Integer, default=0)
    requested_count: Mapped[int] = mapped_column(Integer, default=0)
    attempted_count: Mapped[int] = mapped_column(Integer, default=0)
    claimed_count: Mapped[int] = mapped_column(Integer, default=0)
    learning_status: Mapped[str] = mapped_column(String(16), default="idle")
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("preference_learning_queue", "learning_status", "lease_until"),)


class PreferenceSample(IdentityMixin, Base):
    __tablename__ = "preference_samples"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    discovery_session_id: Mapped[str] = mapped_column(
        ForeignKey("discovery_sessions.id"), unique=True, nullable=False
    )
    choice_id: Mapped[str] = mapped_column(ForeignKey("place_choices.id"), unique=True, nullable=False)
    meal_number: Mapped[int] = mapped_column(Integer, nullable=False)
    prefill_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    active_changes: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    final_conditions: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    request_text: Mapped[str] = mapped_column(Text, nullable=False)
    restaurant_facts: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "meal_number"),)
