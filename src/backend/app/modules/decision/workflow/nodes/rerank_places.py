import logging
from collections.abc import Awaitable, Callable

from app.core.errors import AppError
from app.modules.decision.ports import FoodDecisionLlm
from app.modules.decision.workflow.state import State

log = logging.getLogger("food.decision")


def build(llm: FoodDecisionLlm) -> Callable[[State], Awaitable[State]]:
    async def rerank(state: State) -> State:
        try:
            ranked = await llm.rerank(
                state["places"], state["request"], state["action"], state["old_cuisines"],
            )
        except AppError as error:
            if error.code not in {"LLM_UNAVAILABLE", "LLM_INVALID_OUTPUT"}:
                raise
            log.warning("LLM reranking failed; using rule ranking: %s", error.code)
            ranked = state["places"]
        return {"places": ranked}

    return rerank
