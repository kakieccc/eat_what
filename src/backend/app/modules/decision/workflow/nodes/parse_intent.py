from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import cast

from pydantic import JsonValue

from app.modules.decision.ports import FoodDecisionLlm
from app.modules.decision.schemas import DecisionRequest
from app.modules.decision.workflow.state import State


def build(llm: FoodDecisionLlm) -> Callable[[State], Awaitable[State]]:
    async def parse(state: State) -> State:
        request = DecisionRequest.model_validate(state["request"])
        intent = await llm.parse_intent(request.request_text)
        changes: dict[str, JsonValue] = {}
        if (
            intent.radius_meters is not None
            and intent.radius_meters != request.radius_meters
        ):
            changes["radiusMeters"] = {
                "before": request.radius_meters,
                "after": intent.radius_meters,
            }
        if (
            intent.budget_max is not None
            and Decimal(str(intent.budget_max)) != request.budget_per_person.max
        ):
            changes["budgetMax"] = {
                "before": str(request.budget_per_person.max)
                if request.budget_per_person.max is not None
                else None,
                "after": str(intent.budget_max),
            }
        if intent.excluded_cuisines and set(intent.excluded_cuisines) != set(
            request.excluded_cuisines
        ):
            changes["excludedCuisines"] = {
                "before": list(request.excluded_cuisines),
                "after": cast(
                    JsonValue,
                    list(dict.fromkeys(request.excluded_cuisines + intent.excluded_cuisines)),
                ),
            }
        return {"intent": intent.model_dump(mode="json"), "changes": changes}

    return parse
