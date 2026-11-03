from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    Field,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    StringConstraints,
    field_serializer,
    model_serializer,
    model_validator,
)
from pydantic.alias_generators import to_camel

from app.core.models import Model

SearchRadius = Literal[500, 1000, 2000, 5000]
ALLOWED_FOOD_LIMIT = 5
FoodName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]


class Budget(Model):
    min: Decimal | None = Field(default=None, ge=0, le=10000, decimal_places=2)
    max: Decimal | None = Field(default=None, ge=0, le=10000, decimal_places=2)

    @field_serializer("min", "max", when_used="json")
    def decimal_string(self, value: Decimal | None) -> str | None:
        return format(value.normalize(), "f") if value is not None else None

    @model_validator(mode="after")
    def ordered(self) -> Budget:
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("预算下限不能高于上限")
        return self


class Preferences(Model):
    budget_per_person: Budget = Field(default_factory=Budget)
    radius_meters: SearchRadius = 2000
    excluded_foods: list[FoodName] = Field(default_factory=list, max_length=12)

    allowed_foods: list[FoodName] = Field(default_factory=list, max_length=ALLOWED_FOOD_LIMIT)

    @model_validator(mode="after")
    def categories(self) -> Preferences:
        if set(self.allowed_foods) & set(self.excluded_foods):
            raise ValueError("限定的食物不能同时被排除")
        return self


class AccountPreferences(Preferences):
    request_text: str = Field(default="", max_length=1000)


class PreferenceOverrides(Model):
    budget_per_person: Budget | None = None
    radius_meters: SearchRadius | None = None
    request_text: str | None = Field(default=None, max_length=1000)
    allowed_foods: list[FoodName] | None = Field(default=None, max_length=ALLOWED_FOOD_LIMIT)
    excluded_foods: list[FoodName] | None = Field(default=None, max_length=12)

    @model_serializer(mode="wrap")
    def sparse(self, handler: SerializerFunctionWrapHandler, info: SerializationInfo) -> dict[str, object]:
        # Omitted keys inherit defaults; explicit null budget bounds still pin an unlimited budget.
        keys = {to_camel(key) if info.by_alias else key for key in self.model_fields_set}
        return {key: value for key, value in handler(self).items() if key in keys}

    @model_validator(mode="after")
    def valid_overrides(self) -> PreferenceOverrides:
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("恢复自动学习请移除该字段；不限预算请使用 min/max 为 null")
        if set(self.allowed_foods or []) & set(self.excluded_foods or []):
            raise ValueError("限定的食物不能同时被排除")
        return self


class PreferencesUpdate(Model):
    revision: int = Field(ge=0)
    overrides: PreferenceOverrides


class PreferenceLearningUpdate(Model):
    enabled: bool = Field(strict=True)


class LearningStatus(Model):
    enabled: bool = False
    meal_count: int = 0
    status: Literal["idle", "queued", "running", "failed"] = "idle"
    last_success_at: datetime | None = None
    next_learning_at: int = 10


class PreferencesResponse(Model):
    defaults: AccountPreferences
    sources: dict[str, Literal["manual", "learned", "builtin"]]
    overrides: PreferenceOverrides
    revision: int = 0
    learning: LearningStatus = Field(default_factory=LearningStatus)


class PrefillSnapshot(Model):
    values: AccountPreferences
    source: Literal["defaults", "history"]
    revision: int | None = Field(default=None, ge=0)


class LearnedBudget(Model):
    value: Budget
    sample_ids: list[str] = Field(min_length=3, max_length=20)


class LearnedRadius(Model):
    value: SearchRadius
    sample_ids: list[str] = Field(min_length=3, max_length=20)


class LearnedSoftPreference(Model):
    text: str = Field(min_length=1, max_length=200)
    basis: Literal["requestText", "cuisine"]
    sample_ids: list[str] = Field(min_length=3, max_length=20)


class LearnedPreferences(Model):
    budget_per_person: list[LearnedBudget] = Field(max_length=1)
    radius_meters: list[LearnedRadius] = Field(max_length=1)
    soft_preferences: list[LearnedSoftPreference] = Field(max_length=10)
