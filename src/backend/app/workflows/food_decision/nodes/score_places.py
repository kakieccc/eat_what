from collections.abc import Awaitable, Callable

from app.domain.decision.models import DecisionRequest
from app.domain.decision.policies import score_places
from app.workflows.food_decision.nodes.common import places, serialized
from app.workflows.food_decision.state import State


def build() -> Callable[[State], Awaitable[State]]:
    async def scoring(state: State) -> State:
        request = DecisionRequest.model_validate(state["request"])
        return {
            "places": serialized(
                score_places(
                    places(state),
                    request,
                    state.get("action", ""),
                    state.get("recent", []),
                    state.get("old_cuisines", []),
                )
            )
        }

    return scoring
