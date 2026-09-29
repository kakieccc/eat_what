from collections.abc import Awaitable, Callable
from decimal import Decimal

from pydantic import ValidationError

from app.core.errors import AppError
from app.domain.decision.models import DecisionRequest, Intent
from app.workflows.food_decision.state import State


def build() -> Callable[[State], Awaitable[State]]:
    async def confirm(state: State) -> State:
        request = DecisionRequest.model_validate(state["request"])
        intent = Intent.model_validate(state["intent"])
        updated = request
        if state.get("changes"):
            accepted = state.get("confirmation_answer")
            if accepted is None:
                return {
                    "awaiting_confirmation": True,
                    "resume_from": "confirm_intent",
                }
            if accepted is True:
                if intent.max_walking_minutes is not None:
                    updated = updated.model_copy(
                        update={"max_walking_minutes": intent.max_walking_minutes}
                    )
                if intent.budget_max is not None:
                    updated = updated.model_copy(
                        update={
                            "budget_per_person": updated.budget_per_person.model_copy(
                                update={"max": Decimal(str(intent.budget_max))}
                            )
                        }
                    )
                updated = updated.model_copy(
                    update={
                        "excluded_cuisines": list(
                            dict.fromkeys(request.excluded_cuisines + intent.excluded_cuisines)
                        )
                    }
                )
        preferred_cuisines = [
            cuisine
            for cuisine in list(
                dict.fromkeys(updated.preferred_cuisines + intent.preferred_cuisines)
            )
            if cuisine not in updated.excluded_cuisines
        ]
        updated = updated.model_copy(
            update={
                "preferred_cuisines": preferred_cuisines,
                "desired_tags": list(dict.fromkeys(updated.desired_tags + intent.desired_tags))[:5],
            }
        )
        try:
            validated = DecisionRequest.model_validate(updated.model_dump(mode="json"))
            return {
                "request": validated.model_dump(mode="json"),
                "changes": {},
                "awaiting_confirmation": False,
                "confirmation_answer": None,
                "resume_from": None,
            }
        except ValidationError:
            raise AppError(
                "INVALID_PREFERENCE", "解析后的条件冲突，请修改预算或菜系后重试"
            ) from None

    return confirm
