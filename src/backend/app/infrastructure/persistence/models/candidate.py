from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.models.base import Base, IdentityMixin


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
    walking_distance_meters: Mapped[int | None]
    walking_duration_seconds: Mapped[int | None]
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
    route_snapshot: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    place_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("decision_run_id", "rank"),
        UniqueConstraint("decision_run_id", "place_key"),
        Index("candidate_run_score", "decision_run_id", "score"),
    )
