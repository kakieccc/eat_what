from collections.abc import Awaitable, Callable

from app.modules.decision.schemas import DecisionRequest
from app.modules.decision.workflow.context import execution_deadline
from app.modules.decision.workflow.nodes.common import serialized
from app.modules.decision.workflow.state import State
from app.modules.places.service import PlaceService


def build(places: PlaceService) -> Callable[[State], Awaitable[State]]:
    async def search(state: State) -> State:
        request = DecisionRequest.model_validate(state["request"])
        result = await places.search(
            request.origin, request.radius_meters, deadline=execution_deadline.get()
        )
        return {"places": serialized(result)}

    return search
