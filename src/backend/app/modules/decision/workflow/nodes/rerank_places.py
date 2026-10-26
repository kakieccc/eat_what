from collections.abc import Awaitable, Callable

from app.modules.decision.ports import FoodDecisionLlm
from app.modules.decision.schemas import DecisionRequest
from app.modules.decision.workflow.nodes.common import places, serialized
from app.modules.decision.workflow.state import State


def build(llm: FoodDecisionLlm) -> Callable[[State], Awaitable[State]]:
    async def rerank(state: State) -> State:
        request = DecisionRequest.model_validate(state["request"])
        action = state.get("action", "")
        ranked = await llm.rerank(places(state), request, action, state.get("old_cuisines", []))
        return {"places": serialized(ranked)}

    return rerank
