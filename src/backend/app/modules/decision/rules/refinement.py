from app.core.errors import AppError
from app.modules.decision.schemas import (
    ChangeBudgetRefinement,
    ChangeRadiusRefinement,
    DecisionRequest,
    ExcludePlaceRefinement,
    RefinementRequest,
)


def apply_refinement(
    request: DecisionRequest, refinement: RefinementRequest, previous: list[str]
) -> DecisionRequest:
    if isinstance(refinement, ChangeRadiusRefinement):
        preferences = request.preferences.model_copy(update={"radius_meters": refinement.value})
    elif isinstance(refinement, ChangeBudgetRefinement):
        preferences = request.preferences.model_copy(update={"budget_per_person": refinement.value})
    else:
        if isinstance(refinement, ExcludePlaceRefinement) and refinement.value not in previous:
            raise AppError("NOT_FOUND", "地点不属于本次候选", 404)
        return request
    return request.model_copy(update={"preferences": preferences})
