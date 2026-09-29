from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.models.base import Base, IdentityMixin


class PlaceCache(IdentityMixin, Base):
    __tablename__ = "place_cache"

    cache_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), default="amap")
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class RouteCache(IdentityMixin, Base):
    __tablename__ = "route_cache"

    cache_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    origin_geohash: Mapped[str] = mapped_column(String(32), default="")
    destination_place_id: Mapped[str] = mapped_column(String(128), default="")
    travel_mode: Mapped[str] = mapped_column(String(32), default="walking")
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
