from collections.abc import Awaitable, Callable

from app.modules.decision.ports import FoodDecisionLlm
from app.modules.decision.workflow.state import State


def build(llm: FoodDecisionLlm) -> Callable[[State], Awaitable[State]]:
    async def rerank(state: State) -> State:
        ranked = await llm.rerank(
            state["places"], state["request"], state["action"], state["old_cuisines"],
        )
        return {"places": ranked}

    return rerank
