from collections.abc import Awaitable, Callable

from app.domain.decision.policies import diverse
from app.workflows.food_decision.nodes.common import places, serialized
from app.workflows.food_decision.state import State


def build() -> Callable[[State], Awaitable[State]]:
    async def select(state: State) -> State:
        return {"places": serialized(diverse(places(state)))}

    return select
