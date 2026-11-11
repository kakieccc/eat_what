import asyncio
from collections.abc import Awaitable, Callable

from app.core.config import settings
from app.core.errors import AppError
from app.modules.decision.rules.policies import eligible
from app.modules.decision.workflow.context import execution_deadline
from app.modules.decision.workflow.state import State
from app.modules.places.schemas import Place
from app.modules.places.service import PlaceService


def build(places: PlaceService) -> Callable[[State], Awaitable[State]]:
    async def search(state: State) -> State:
        request = state["request"]
        keywords = list(dict.fromkeys(request.preferences.allowed_foods)) or [""]
        # Missing means the first search; an empty queue means its directions were exhausted.
        if "search_queue" in state:
            queue = list(state["search_queue"])
            fallback_used = state["search_fallback_used"]
        else:
            queue = [(word, 1) for word in keywords]
            fallback_used = keywords == [""]
        unique: dict[str, Place] = {p.id: p for p in state["places"]}
        seen = set(state.get("search_seen_ids", []))
        seen.update(unique)
        summary = dict(state["filter_summary"])
        calls = summary.get("searchRequests", 0)
        failures = summary.get("searchFailures", 0)
        last_error: AppError | None = None
        if not queue and len(unique) < settings.decision_candidate_limit and not fallback_used:
            queue.append(("", 1))
            fallback_used = True
        while queue and calls < settings.decision_search_limit:
            word, page = queue.pop(0)
            calls += 1
            try:
                result = await places.search(
                    request.origin,
                    request.preferences.radius_meters,
                    limit=25,
                    keywords=[word] if word else [],
                    page=page,
                    deadline=execution_deadline.get(),
                )
                batch = result.places
                has_more = result.has_more
            except AppError as error:
                deadline = execution_deadline.get()
                if deadline is not None and asyncio.get_running_loop().time() >= deadline:
                    raise TimeoutError from error
                if error.code not in {"AMAP_UNAVAILABLE", "AMAP_SCHEMA_ERROR", "AMAP_INVALID_RESPONSE"}:
                    raise
                failures += 1
                last_error = error
                batch = []
                has_more = False
            fresh = []
            for place in batch:
                if place.id not in seen:
                    # Rejected candidates must not return in later supplement searches.
                    seen.add(place.id)
                    fresh.append(place)
            kept, counts = eligible(fresh, request, state["excluded"])
            unique.update((p.id, p) for p in kept)
            for key, count in counts.items():
                summary[key] = summary.get(key, 0) + count
            if has_more:
                queue.append((word, page + 1))
            if not queue and len(unique) < settings.decision_candidate_limit and not fallback_used:
                queue.append(("", 1))
                fallback_used = True
            # Give each search direction its first page before stopping.
            if len(unique) >= settings.decision_candidate_limit and calls >= len(keywords):
                break
        if failures == calls and last_error is not None:
            raise last_error
        summary.update(
            retrieved=len(seen),
            searchRequests=calls,
            searchFailures=failures,
            searchBudgetExhausted=int(bool(queue) and calls >= settings.decision_search_limit),
        )
        return {
            "places": list(unique.values()), "filter_summary": summary,
            "search_queue": queue, "search_seen_ids": list(seen),
            "search_fallback_used": fallback_used,
        }

    return search
