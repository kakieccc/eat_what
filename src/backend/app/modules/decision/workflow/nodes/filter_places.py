import asyncio
from collections.abc import Awaitable, Callable

from app.core.concurrency import gather_cancel_on_error
from app.core.errors import AppError
from app.modules.decision.rules.policies import eligible, score_places
from app.modules.decision.schemas import DecisionRequest
from app.modules.decision.workflow.context import execution_deadline
from app.modules.decision.workflow.nodes.common import places, serialized
from app.modules.decision.workflow.state import State
from app.modules.places.schemas import Place
from app.modules.places.service import PlaceService


def merge_detail(place: Place, detail: Place) -> Place:
    if place.id != detail.id:
        raise AppError("AMAP_INVALID_RESPONSE", "地点详情与候选不一致", 502)
    fields = (
        "name",
        "category_code",
        "category_name",
        "cuisine_types",
        "tags",
        "address",
        "location",
        "straight_line_distance_meters",
        "rating",
        "average_cost",
        "opening_hours_text",
        "phone",
        "photos",
    )
    updates = {}
    timestamps = {key: place.data_updated_at for key in fields} | place.field_updated_at
    for key in fields:
        value = getattr(detail, key)
        if (
            value is not None
            and value != ""
            and value != []
            and detail.data_updated_at >= timestamps[key]
        ):
            updates[key] = value
            timestamps[key] = detail.data_updated_at
    updates["field_updated_at"] = timestamps
    return place.model_copy(update=updates)


def build(service: PlaceService) -> Callable[[State], Awaitable[State]]:
    async def filtering(state: State) -> State:
        request = DecisionRequest.model_validate(state["request"])
        ordered = score_places(
            places(state),
            request,
            state.get("action", ""),
            state.get("recent", []),
            state.get("old_cuisines", []),
        )[:10]
        if not ordered:
            return {"places": []}

        async def detail_or_search(p: Place) -> tuple[Place, bool]:
            try:
                detail = await service.detail(
                    p.external_id, request.origin, deadline=execution_deadline.get()
                )
                return merge_detail(p, detail), False
            except AppError as error:
                deadline = execution_deadline.get()
                if deadline is not None and asyncio.get_running_loop().time() >= deadline:
                    raise TimeoutError from error
                if error.code not in {"AMAP_UNAVAILABLE", "AMAP_SCHEMA_ERROR", "AMAP_INVALID_RESPONSE"}:
                    raise
                return p.model_copy(update={"warnings": list(dict.fromkeys([
                    *p.warnings, "详情暂不可用，使用搜索信息",
                ]))}), True

        details = await gather_cancel_on_error(*(detail_or_search(p) for p in ordered))
        merged = [p for p, _ in details]
        kept, counts = eligible(merged, request, state.get("excluded", []))
        summary = {
            **state.get("filter_summary", {}), "detailRequests": len(details),
            "detailFailures": sum(failed for _, failed in details),
        }
        for key, count in counts.items():
            summary[key] = summary.get(key, 0) + count
        rescored = score_places(
            kept,
            request,
            state.get("action", ""),
            state.get("recent", []),
            state.get("old_cuisines", []),
        )
        return {"places": serialized(rescored), "filter_summary": summary}

    return filtering
