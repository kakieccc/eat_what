from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from app.core.models import Model

SearchRadius = Literal[500, 1000, 2000, 5000]


class Budget(Model):
    min: Decimal | None = Field(default=None, ge=0, le=10000)
    max: Decimal | None = Field(default=None, ge=0, le=10000)

    @model_validator(mode="after")
    def ordered(self) -> Budget:
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("预算下限不能高于上限")
        return self


class Preferences(Model):
    budget_per_person: Budget = Field(default_factory=Budget)
    radius_meters: SearchRadius = 2000
    preferred_foods: list[str] = Field(default_factory=list, max_length=12)
    excluded_foods: list[str] = Field(default_factory=list, max_length=12)
    soft_preferences: list[str] = Field(default_factory=list, max_length=5)

    allowed_foods: list[str] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def categories(self) -> Preferences:
        if any(
            not c.strip() or len(c) > 30
            for c in self.preferred_foods + self.excluded_foods + self.allowed_foods
        ):
            raise ValueError("食物名称须为 1–30 字")
        if set(self.preferred_foods + self.allowed_foods) & set(self.excluded_foods):
            raise ValueError("偏好或限定的食物不能同时被排除")
        if any(not t.strip() or len(t) > 30 for t in self.soft_preferences):
            raise ValueError("软偏好须为 1–30 字")
        return self


class PreferencesUpdate(Preferences):
    radius_meters: SearchRadius = 2000
