from app.core.errors import AppError
from app.modules.decision.schemas import (
    ChangeBudgetRefinement,
    DecisionRequest,
    ExcludePlaceRefinement,
    IncreaseWalkingRefinement,
    RefinementRequest,
)


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
