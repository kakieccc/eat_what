from collections.abc import Awaitable, Callable

from app.domain.decision.models import DecisionRequest
from app.domain.places.ports import GeoPlaceProvider
from app.workflows.food_decision.nodes.common import serialized
from app.workflows.food_decision.state import State


def build(amap: GeoPlaceProvider) -> Callable[[State], Awaitable[State]]:
    async def search(state: State) -> State:
        request = DecisionRequest.model_validate(state["request"])
        return {"places": serialized(await amap.search(request.origin, request.radius_meters))}

    return search
