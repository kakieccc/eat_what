from collections.abc import Awaitable, Callable

from app.modules.decision.ports import FoodDecisionLlm
from app.modules.decision.workflow.nodes.common import places, serialized
from app.modules.decision.workflow.state import State
from app.modules.places.service import PlaceService


def build(place_service: PlaceService, llm: FoodDecisionLlm) -> Callable[[State], Awaitable[State]]:
    async def explain(state: State) -> State:
        selected = places(state)
        if not selected:
            return {"places": []}
        explained = await llm.explain(selected)
        return {"places": serialized([place_service.with_navigation(p) for p in explained])}

    return explain
