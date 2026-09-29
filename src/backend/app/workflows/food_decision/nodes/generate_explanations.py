import asyncio
from collections.abc import Awaitable, Callable

from app.domain.decision.models import DecisionRequest
from app.domain.decision.ports import FoodDecisionLlm
from app.domain.places.ports import GeoPlaceProvider
from app.workflows.food_decision.nodes.common import places, serialized
from app.workflows.food_decision.state import State


def build(amap: GeoPlaceProvider, llm: FoodDecisionLlm) -> Callable[[State], Awaitable[State]]:
    async def explain(state: State) -> State:
        request = DecisionRequest.model_validate(state["request"])
        selected = places(state)
        details = await asyncio.gather(
            *(amap.detail(place.external_id, request.origin) for place in selected)
        )
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
