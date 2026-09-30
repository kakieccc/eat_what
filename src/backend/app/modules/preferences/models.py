from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, IdentityMixin


class Preference(IdentityMixin, Base):
    __tablename__ = "preferences"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)

    preferred_cuisines: Mapped[list[str]] = mapped_column(JSONB, default=list)
    excluded_cuisines: Mapped[list[str]] = mapped_column(JSONB, default=list)
    disliked_places: Mapped[list[str]] = mapped_column(JSONB, default=list)
    typical_budget_per_person_min: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    typical_budget_per_person_max: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    typical_max_walking_minutes: Mapped[int | None]
    preferred_tags: Mapped[list[str]] = mapped_column(JSONB, default=list)
