from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import now
from app.infrastructure.database.base import Base, IdentityMixin


class PlaceChoice(IdentityMixin, Base):
    __tablename__ = "place_choices"

    __table_args__ = (UniqueConstraint("discovery_session_id"),)
    selected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    discovery_session_id: Mapped[str] = mapped_column(
        ForeignKey("discovery_sessions.id"), nullable=False
    )
    place_candidate_id: Mapped[str] = mapped_column(
        ForeignKey("place_candidates.id"), nullable=False
    )
