from app.core.errors import AppError
from app.modules.decision.schemas import (
    ChangeBudgetRefinement,
    ChangeRadiusRefinement,
    DecisionRequest,
    ExcludePlaceRefinement,
    RefinementRequest,
)
from app.modules.preferences.rules import require_supported_radius


def apply_refinement(
    request: DecisionRequest, refinement: RefinementRequest, previous: list[str]
) -> DecisionRequest:
    data = request.model_dump(mode="python")
    if isinstance(refinement, ChangeRadiusRefinement):
        data["radius_meters"] = refinement.value
    elif isinstance(refinement, ChangeBudgetRefinement):
        data["budget_per_person"] = refinement.value.model_dump(mode="python")
    elif isinstance(refinement, ExcludePlaceRefinement) and refinement.value not in previous:
        raise AppError("NOT_FOUND", "地点不属于本次候选", 404)
    data["request_text"] = ""
    require_supported_radius(int(data["radius_meters"]))
    return DecisionRequest.model_validate(data)
