from __future__ import annotations

from pydantic import Field

from app.domain.base import Model
from app.domain.geo.models import Origin
from app.domain.preferences.models import Preferences


class DecisionRequest(Preferences):
    origin: Origin


class Intent(Model):
    preferred_cuisines: list[str] = Field(default_factory=list, max_length=5)
    excluded_cuisines: list[str] = Field(default_factory=list, max_length=5)
    desired_tags: list[str] = Field(default_factory=list, max_length=5)
    max_walking_minutes: int | None = Field(default=None, ge=1, le=60)
    budget_max: float | None = Field(default=None, ge=0, le=10000)
