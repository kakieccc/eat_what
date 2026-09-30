from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, JsonValue

from app.core.models import Model
from app.modules.location.schemas import Origin
from app.modules.places.schemas import Place
from app.modules.preferences.schemas import Budget, Preferences


class DecisionRequest(Preferences):
    origin: Origin


class Intent(Model):
    preferred_cuisines: list[str] = Field(default_factory=list, max_length=5)
    excluded_cuisines: list[str] = Field(default_factory=list, max_length=5)
    desired_tags: list[str] = Field(default_factory=list, max_length=5)
    max_walking_minutes: int | None = Field(default=None, ge=1, le=60)
    budget_max: float | None = Field(default=None, ge=0, le=10000)


class Ranking(Model):
    place_ids: list[str] = Field(min_length=1, max_length=10)


class Explanation(Model):
    place_id: str
    fragments: list[str] = Field(min_length=1, max_length=3)


class Explanations(Model):
    places: list[Explanation] = Field(min_length=1, max_length=3)


class ConfirmationChange(Model):
    before: JsonValue
    after: JsonValue


class DecisionRunResponse(Model):
    decision_run_id: str
    discovery_session_id: str
    status: Literal["pending", "running", "awaitingConfirmation", "completed", "failed"]
    request: DecisionRequest
    places: list[Place] = Field(default_factory=list)
    confirmation: dict[str, ConfirmationChange] | None = None
    filter_summary: dict[str, int] = Field(default_factory=dict)
    suggestions: list[str] = Field(default_factory=list)
    error_code: str | None = None
    chosen_candidate_ids: list[str] = Field(default_factory=list)


class DecisionCreateRequest(DecisionRequest):
    pass


class DecisionRunUpdateRequest(Model):
    accept_changes: bool | None = None


class SimpleRefinement(Model):
    action: Literal["closer", "cheaper", "higherRated", "differentCuisine", "refresh"]
    value: None = None


class ExcludePlaceRefinement(Model):
    action: Literal["excludePlace"]
    value: str = Field(min_length=1, max_length=100)


class IncreaseWalkingRefinement(Model):
    action: Literal["increaseWalkingLimit"]
    value: int = Field(ge=1, le=60)


class ChangeBudgetRefinement(Model):
    action: Literal["changeBudget"]
    value: Budget


RefinementRequest = Annotated[
    SimpleRefinement | ExcludePlaceRefinement | IncreaseWalkingRefinement | ChangeBudgetRefinement,
    Field(discriminator="action"),
]
