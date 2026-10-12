import asyncio
from collections.abc import Awaitable, Callable

from app.core.concurrency import deadline_after, gather_cancel_on_error
from app.modules.decision.ports import FoodDecisionLlm
from app.modules.decision.schemas import DecisionRequest
from app.modules.decision.workflow.context import execution_deadline
from app.modules.decision.workflow.nodes.common import places, serialized
from app.modules.decision.workflow.state import State
from app.modules.places.ports import GeoPlaceProvider
from app.modules.places.service import PlaceService


def build(
    amap: GeoPlaceProvider, place_service: PlaceService, llm: FoodDecisionLlm
) -> Callable[[State], Awaitable[State]]:
    async def explain(state: State) -> State:
        request = DecisionRequest.model_validate(state["request"])
        selected = places(state)
        deadline = deadline_after(place_service.timeout_seconds, execution_deadline.get())
        async with asyncio.timeout_at(deadline):
            details = await gather_cancel_on_error(*(
                place_service.detail(place.external_id, request.origin, deadline=deadline)
                for place in selected
            ))
        selected = [
            place.model_copy(update={"phone": detail.phone, "photos": detail.photos})
            for place, detail in zip(selected, details, strict=True)
        ]
        explained = await llm.explain(selected)
        return {
            "places": serialized(
                [
                    place.model_copy(
                        update={"navigation_url": amap.navigation(request.origin, place)}
                    )
                    for place in explained
                ]
            )
        }

    return explain
