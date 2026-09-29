from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.models.base import Base, IdentityMixin


class PlaceChoice(IdentityMixin, Base):
    __tablename__ = "place_choices"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    discovery_session_id: Mapped[str] = mapped_column(
        ForeignKey("discovery_sessions.id"), nullable=False
    )
    place_candidate_id: Mapped[str] = mapped_column(
        ForeignKey("place_candidates.id"), nullable=False
    )
    feedback: Mapped[str] = mapped_column(String(300), default="")
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "idempotency_key"),)
