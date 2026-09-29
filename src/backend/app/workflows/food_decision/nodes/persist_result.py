from collections.abc import Awaitable, Callable

from app.workflows.food_decision.context import Persist
from app.workflows.food_decision.state import State


def build(persist: Persist) -> Callable[[State], Awaitable[State]]:
    async def save(state: State) -> State:
        await persist(state)
        return {"persisted": True}

    return save
