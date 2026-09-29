from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from app.domain.base import Model

CUISINES = [
    "中餐",
    "面馆",
    "火锅",
    "烧烤",
    "快餐",
    "轻食",
    "日韩料理",
    "东南亚料理",
    "西餐",
    "咖啡甜品",
    "小吃",
    "其他餐饮",
]


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
    max_walking_minutes: int = Field(default=15, ge=1, le=60)
    radius_meters: int = Field(default=2000, ge=100, le=50000)
    preferred_cuisines: list[str] = Field(default_factory=list, max_length=12)
    excluded_cuisines: list[str] = Field(default_factory=list, max_length=12)
    desired_tags: list[str] = Field(default_factory=list, max_length=5)
    meal_period: Literal["breakfast", "lunch", "dinner", "lateNight"] = "lunch"
    party_size: int = Field(default=1, ge=1, le=20)
    open_now_preferred: bool = True
    request_text: str = Field(default="", max_length=300)

    @model_validator(mode="after")
    def categories(self) -> Preferences:
        if any(c not in CUISINES for c in self.preferred_cuisines + self.excluded_cuisines):
            raise ValueError("不支持的菜系")
        if set(self.preferred_cuisines) & set(self.excluded_cuisines):
            raise ValueError("喜欢和排除的菜系不能重叠")
        if any(len(t) > 30 for t in self.desired_tags):
            raise ValueError("场景标签过长")
        return self
