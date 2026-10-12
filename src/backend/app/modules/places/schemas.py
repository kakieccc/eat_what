from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.core.models import Model
from app.modules.location.schemas import Point


class Place(Model):
    id: str
    external_id: str
    source: Literal["amap"] = "amap"
    name: str
    category_code: str
    category_name: str
    cuisine_types: list[str]
    address: str
    location: Point
    straight_line_distance_meters: int = Field(ge=0)
    rating: float | None = Field(default=None, ge=0, le=5)
    average_cost: Decimal | None = Field(default=None, ge=0)
    business_status: Literal["open", "closed", "unknown"] = "unknown"
    opening_hours_text: str | None = None
    phone: str | None = None
    photos: list[str] = Field(default_factory=list)
    data_updated_at: datetime
    score: float = 0
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    reason: str = ""
    warnings: list[str] = Field(default_factory=list)
    navigation_url: str | None = None
    candidate_id: str | None = None
    rank: int = 0
