from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.models.base import Base, IdentityMixin


class DiscoverySession(IdentityMixin, Base):
    __tablename__ = "discovery_sessions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    origin_latitude: Mapped[float] = mapped_column(nullable=False)
    origin_longitude: Mapped[float] = mapped_column(nullable=False)
    origin_address: Mapped[str] = mapped_column(String(200), default="")
    budget_per_person_min: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    budget_per_person_max: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    max_walking_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    radius_meters: Mapped[int] = mapped_column(Integer, nullable=False)
    preferred_cuisines: Mapped[list[str]] = mapped_column(JSONB, default=list)
    excluded_cuisines: Mapped[list[str]] = mapped_column(JSONB, default=list)
    desired_tags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    meal_period: Mapped[str] = mapped_column(String(32), nullable=False)
    party_size: Mapped[int] = mapped_column(Integer, nullable=False)
    open_now_preferred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    request_text: Mapped[str] = mapped_column(String(300), default="")
    normalized_preferences: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
