from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from app.core.errors import AppError
from app.domain.base import Model
from app.domain.decision.models import DecisionRequest
from app.domain.preferences.models import Budget


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


def apply_refinement(
    request: DecisionRequest, refinement: RefinementRequest, previous: list[str]
) -> DecisionRequest:
    data = request.model_dump(mode="python")
    if isinstance(refinement, IncreaseWalkingRefinement):
        if refinement.value <= request.max_walking_minutes:
            raise AppError("INVALID_REFINEMENT", "新步行上限必须大于原上限")
        data["max_walking_minutes"] = refinement.value
    elif isinstance(refinement, ChangeBudgetRefinement):
        data["budget_per_person"] = refinement.value.model_dump(mode="python")
    elif isinstance(refinement, ExcludePlaceRefinement) and refinement.value not in previous:
        raise AppError("NOT_FOUND", "地点不属于本次候选", 404)
    data["request_text"] = ""
    return DecisionRequest.model_validate(data)
