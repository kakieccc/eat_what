import asyncio
from collections.abc import Awaitable, Callable

from app.modules.decision.rules.policies import eligible
from app.modules.decision.schemas import DecisionRequest
from app.modules.decision.workflow.nodes.common import places, serialized
from app.modules.decision.workflow.state import State
from app.modules.places.ports import GeoPlaceProvider


def build(amap: GeoPlaceProvider) -> Callable[[State], Awaitable[State]]:
    async def routes(state: State) -> State:
        request = DecisionRequest.model_validate(state["request"])
        candidates = places(state)[:8]
        async with asyncio.timeout(7):
            routed = await asyncio.gather(
                *(amap.walking(request.origin, place.location) for place in candidates)
            )
        enriched = [
            place.model_copy(update={"route": route})
            for place, route in zip(candidates, routed, strict=True)
        ]
        kept, counts = eligible(enriched, request, state.get("excluded", []), routes=True)
        summary = state.get("filter_summary", {}).copy()
        for key, value in counts.items():
            summary[key] = summary.get(key, 0) + value
        return {"places": serialized(kept), "filter_summary": summary}

    return routes
