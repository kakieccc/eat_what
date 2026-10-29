import asyncio
from collections.abc import Awaitable, Callable

from app.core.concurrency import gather_cancel_on_error
from app.core.errors import AppError
from app.modules.decision.ports import FoodDecisionLlm
from app.modules.decision.rules.policies import eligible, score_places
from app.modules.decision.schemas import DecisionRequest
from app.modules.decision.workflow.context import execution_deadline
from app.modules.decision.workflow.nodes.common import places, serialized
from app.modules.decision.workflow.nodes.search_places import CANDIDATE_LIMIT
from app.modules.decision.workflow.nodes.search_places import build as build_search
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


def build(service: PlaceService, llm: FoodDecisionLlm) -> Callable[[State], Awaitable[State]]:
    search_more = build_search(service)

    async def filtering(state: State) -> State:
        request = DecisionRequest.model_validate(state["request"])

        def ranked(candidates: list[Place]) -> list[Place]:
            return score_places(
                candidates, request, state["action"], state["recent"],
            )

        async def detail_or_none(p: Place) -> Place | None:
            try:
                detail = await service.detail(
                    p.external_id, request.origin, deadline=execution_deadline.get()
                )
                return merge_detail(p, detail)
            except AppError as error:
                deadline = execution_deadline.get()
                if deadline is not None and asyncio.get_running_loop().time() >= deadline:
                    raise TimeoutError from error
                if error.code not in {"PLACE_NOT_FOUND", "AMAP_UNAVAILABLE", "AMAP_SCHEMA_ERROR", "AMAP_INVALID_RESPONSE"}:
                    raise
                return None

        current = state.copy()
        pending = ranked(places(state))
        checked: set[str] = set()
        kept: list[Place] = []
        summary = dict(state["filter_summary"])
        while len(kept) < CANDIDATE_LIMIT:
            if not pending:
                more = await search_more({
                    **current, "places": serialized(kept), "filter_summary": summary,
                })
                current.update(more)
                summary = more["filter_summary"]
                pending = ranked([p for p in places(more) if p.id not in checked])
                if not pending:
                    break
            batch_size = CANDIDATE_LIMIT - len(kept)
            batch, pending = pending[:batch_size], pending[batch_size:]
            checked.update(p.id for p in batch)
            details = await gather_cancel_on_error(*(detail_or_none(p) for p in batch))
            valid, counts = eligible(
                [p for p in details if p is not None], request, state["excluded"]
            )
            food_valid = await llm.filter_foods(valid, request)
            counts["foodRequirements"] = len(valid) - len(food_valid)
            kept.extend(food_valid)
            summary["detailRequests"] = summary.get("detailRequests", 0) + len(details)
            summary["detailFailures"] = summary.get("detailFailures", 0) + sum(p is None for p in details)
            for key, count in counts.items():
                summary[key] = summary.get(key, 0) + count
        return {**current, "places": serialized(ranked(kept)), "filter_summary": summary}

    return filtering
