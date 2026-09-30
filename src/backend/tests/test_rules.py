from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.errors import AppError
from app.modules.decision.rules.policies import diverse, eligible, score_places
from app.modules.decision.rules.refinement import apply_refinement
from app.modules.decision.schemas import ExcludePlaceRefinement, IncreaseWalkingRefinement
from app.modules.location.geometry import distance
from app.modules.preferences.schemas import Budget, Preferences


def test_filter_respects_budget_and_exclusions_without_discarding_unknown_cost(place):
    expensive = place.model_copy(update={"id": "expensive", "average_cost": Decimal(80)})
    unknown = place.model_copy(update={"id": "unknown", "average_cost": None})
    closed = place.model_copy(update={"id": "closed", "business_status": "closed"})
    preferences = Preferences(budget_per_person=Budget(max=40))
    kept, reasons = eligible([place, expensive, unknown, closed], preferences, [place.id])
    assert [item.id for item in kept] == ["unknown"]
    assert kept[0].warnings == ["人均暂无数据，无法确认符合预算"]
    assert reasons == {"excludedPlace": 1, "budget": 1, "closed": 1}


def test_scoring_is_deterministic_and_diversity_limits_selection(place):
    candidates = [place.model_copy(update={"id": f"p{i}", "name": f"店铺{i}"}) for i in range(5)]
    scored = score_places(list(reversed(candidates)), Preferences())
    assert [item.id for item in scored] == ["p0", "p1", "p2", "p3", "p4"]
    assert all(item.score_breakdown["total"] == item.score for item in scored)
    assert len(diverse(scored)) == 3


def test_refinement_validates_membership_and_increasing_limit(decision_request):
    with pytest.raises(AppError, match="NOT_FOUND"):
        apply_refinement(
            decision_request,
            ExcludePlaceRefinement(action="excludePlace", value="other"),
            ["candidate"],
        )
    with pytest.raises(AppError, match="INVALID_REFINEMENT"):
        apply_refinement(
            decision_request, IncreaseWalkingRefinement(action="increaseWalkingLimit", value=15), []
        )
    updated = apply_refinement(
        decision_request.model_copy(update={"request_text": "原始条件"}),
        IncreaseWalkingRefinement(action="increaseWalkingLimit", value=25),
        [],
    )
    assert updated.max_walking_minutes == 25
    assert updated.request_text == ""
    assert decision_request.max_walking_minutes == 15


def test_schema_constraints_and_aliases(decision_request):
    with pytest.raises(ValidationError):
        Preferences(preferred_cuisines=["面馆"], excluded_cuisines=["面馆"])
    with pytest.raises(ValidationError):
        Budget(min=50, max=20)
    payload = decision_request.model_dump(mode="json", by_alias=True)
    assert payload["maxWalkingMinutes"] == 15
    assert "max_walking_minutes" not in payload
    assert distance(decision_request.origin, decision_request.origin) == 0
