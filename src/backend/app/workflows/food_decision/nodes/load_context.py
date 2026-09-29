from collections.abc import Awaitable, Callable

from app.domain.decision.models import DecisionRequest
from app.workflows.food_decision.state import State


def build() -> Callable[[State], Awaitable[State]]:
    async def load(state: State) -> State:
        DecisionRequest.model_validate(state["request"])
        return {"schema_version": 3}

    return load
