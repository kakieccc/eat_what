from collections.abc import Awaitable, Callable

from app.domain.decision.models import DecisionRequest
from app.domain.decision.ports import FoodDecisionLlm
from app.workflows.food_decision.nodes.common import places, serialized
from app.workflows.food_decision.state import State


def build(llm: FoodDecisionLlm) -> Callable[[State], Awaitable[State]]:
    async def rerank(state: State) -> State:
        return {
            "places": serialized(
                await llm.rerank(places(state), DecisionRequest.model_validate(state["request"]))
            )
        }

    return rerank
