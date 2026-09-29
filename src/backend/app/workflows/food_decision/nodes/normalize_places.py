from collections.abc import Awaitable, Callable

from app.workflows.food_decision.nodes.common import places, serialized
from app.workflows.food_decision.state import State


def build() -> Callable[[State], Awaitable[State]]:
    async def normalize(state: State) -> State:
        return {"places": serialized(places(state))}

    return normalize
