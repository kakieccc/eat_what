from collections.abc import Awaitable, Callable

from app.modules.decision.schemas import DecisionRequest
from app.modules.decision.workflow.nodes.common import serialized
from app.modules.decision.workflow.state import State
from app.modules.places.ports import GeoPlaceProvider


def build(amap: GeoPlaceProvider) -> Callable[[State], Awaitable[State]]:
    async def search(state: State) -> State:
        request = DecisionRequest.model_validate(state["request"])
        return {"places": serialized(await amap.search(request.origin, request.radius_meters))}

    return search
