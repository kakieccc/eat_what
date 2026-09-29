from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.models.base import Base, IdentityMixin


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
