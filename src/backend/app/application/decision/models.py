from __future__ import annotations

from typing import Literal

from pydantic import Field, JsonValue

from app.domain.base import Model
from app.domain.decision.models import DecisionRequest
from app.domain.decision.refinement import (
    ChangeBudgetRefinement,
    ExcludePlaceRefinement,
    IncreaseWalkingRefinement,
    RefinementRequest,
    SimpleRefinement,
)
from app.domain.places.models import Place


class DecisionRunResponse(Model):
    decision_run_id: str
    discovery_session_id: str
    status: Literal["pending", "running", "awaitingConfirmation", "completed", "failed"]
    request: DecisionRequest
    places: list[Place] = Field(default_factory=list)
    confirmation: dict[str, JsonValue] | None = None
    filter_summary: dict[str, int] = Field(default_factory=dict)
    suggestions: list[str] = Field(default_factory=list)
    error_code: str | None = None
    chosen_candidate_ids: list[str] = Field(default_factory=list)


__all__ = [
    "ChangeBudgetRefinement",
    "DecisionRunResponse",
    "ExcludePlaceRefinement",
    "IncreaseWalkingRefinement",
    "RefinementRequest",
    "SimpleRefinement",
]
