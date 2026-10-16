from collections.abc import Awaitable, Callable

from app.modules.decision.ports import FoodDecisionLlm
from app.modules.decision.schemas import DecisionIntent, DecisionRequest
from app.modules.decision.workflow.nodes.common import places, serialized
from app.modules.decision.workflow.state import State


def build(llm: FoodDecisionLlm) -> Callable[[State], Awaitable[State]]:
    async def rerank(state: State) -> State:
        candidates = places(state)
        ranked = await llm.rerank(
            candidates,
            DecisionRequest.model_validate(state["request"]),
            DecisionIntent.model_validate(state["intent"]),
            state.get("action", ""),
            state.get("old_cuisines", []),
        )
        return {
            "places": serialized(ranked),
            "filter_summary": {
                **state.get("filter_summary", {}),
                "requirements": len(candidates) - len(ranked),
            },
        }

    return rerank
