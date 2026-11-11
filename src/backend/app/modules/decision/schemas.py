from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from app.core.config import settings
from app.core.models import Model
from app.modules.choice.schemas import ChoiceSnapshot
from app.modules.location.schemas import Origin
from app.modules.places.schemas import Place
from app.modules.preferences.schemas import (
    ALLOWED_FOOD_LIMIT,
    Budget,
    Preferences,
    PrefillSnapshot,
    SearchRadius,
)


class DecisionRequest(Model):
    origin: Origin
    preferences: Preferences = Field(default_factory=Preferences)
    meal_period: Literal["breakfast", "lunch", "dinner", "lateNight"] = "lunch"
    party_size: int = Field(default=1, ge=1, le=20, strict=True)
    request_text: str = Field(default="", max_length=1000)


class ConditionAssessment(Model):
    term: str = Field(min_length=1, max_length=30)
    status: Literal["match", "mismatch", "unknown"]
    evidence: list[str] = Field(default_factory=list, max_length=5)


class FoodAssessment(Model):
    place_id: str
    allowed: list[ConditionAssessment] = Field(default_factory=list, max_length=ALLOWED_FOOD_LIMIT)
    excluded: list[ConditionAssessment] = Field(default_factory=list, max_length=12)


class FoodAssessments(Model):
    places: list[FoodAssessment] = Field(min_length=1, max_length=settings.decision_candidate_limit)


class MatchScore(Model):
    place_id: str
    score: float = Field(ge=0, le=100, allow_inf_nan=False, strict=True)
    evidence: list[str] = Field(max_length=5)


class Ranking(Model):
    places: list[MatchScore] = Field(min_length=1, max_length=settings.decision_candidate_limit)


class DecisionRunResponse(Model):
    decision_run_id: str
    discovery_session_id: str
    status: Literal["pending", "running", "completed", "failed"]
    request: DecisionRequest
    places: list[Place] = Field(default_factory=list)
    original_request: DecisionRequest
    filter_summary: dict[str, int] = Field(default_factory=dict)
    suggestions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error_code: str | None = None
    choice: ChoiceSnapshot | None = None


class DecisionCreateRequest(DecisionRequest):
    prefill_snapshot: PrefillSnapshot


class SimpleRefinement(Model):
    action: Literal["closer", "cheaper", "higherRated", "differentCuisine", "refresh"]
    value: None = None


class ExcludePlaceRefinement(Model):
    action: Literal["excludePlace"]
    value: str = Field(min_length=1, max_length=100)


class ChangeRadiusRefinement(Model):
    action: Literal["changeRadius"]
    value: SearchRadius


class ChangeBudgetRefinement(Model):
    action: Literal["changeBudget"]
    value: Budget


RefinementRequest = Annotated[
    SimpleRefinement | ExcludePlaceRefinement | ChangeRadiusRefinement | ChangeBudgetRefinement,
    Field(discriminator="action"),
]
