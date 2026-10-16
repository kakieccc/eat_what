import asyncio
from collections.abc import Awaitable, Callable

from app.core.errors import AppError
from app.modules.decision.rules.policies import eligible
from app.modules.decision.schemas import DecisionRequest
from app.modules.decision.workflow.context import execution_deadline
from app.modules.decision.workflow.nodes.common import serialized
from app.modules.decision.workflow.state import State
from app.modules.places.schemas import Place
from app.modules.places.service import PlaceService


def build(places: PlaceService) -> Callable[[State], Awaitable[State]]:
    async def search(state: State) -> State:
        request = DecisionRequest.model_validate(state["request"])
        keywords = list(dict.fromkeys(state.get("search_keywords", [])))[:5] or [""]
        queue = [(word, 1) for word in keywords]
        unique: dict[str, Place] = {}
        kept: list[Place] = []
        summary: dict[str, int] = {}
        calls = 0
        failures = 0
        last_error: AppError | None = None
        fallback_used = keywords == [""]
        while queue and calls < 8:
            word, page = queue.pop(0)
            calls += 1
            try:
                batch = await places.search(
                    request.origin,
                    request.preferences.radius_meters,
                    limit=25,
                    keywords=[word] if word else [],
                    page=page,
                    deadline=execution_deadline.get(),
                )
            except AppError as error:
                deadline = execution_deadline.get()
                if deadline is not None and asyncio.get_running_loop().time() >= deadline:
                    raise TimeoutError from error
                if error.code not in {"AMAP_UNAVAILABLE", "AMAP_SCHEMA_ERROR", "AMAP_INVALID_RESPONSE"}:
                    raise
                failures += 1
                last_error = error
                batch = []
            unique.update((p.id, p) for p in batch)
            kept, summary = eligible(list(unique.values()), request, state.get("excluded", []))
            if len(batch) == 25:
                queue.append((word, page + 1))
            if not queue and len(kept) < 10 and not fallback_used:
                queue.append(("", 1))
                fallback_used = True
            # Give each search direction its first page before stopping.
            if len(kept) >= 10 and calls >= len(keywords):
                break
        if failures == calls and last_error is not None:
            raise last_error
        summary.update(
            retrieved=len(unique),
            searchRequests=calls,
            searchFailures=failures,
            searchBudgetExhausted=int(bool(queue) and calls == 8),
        )
        return {"places": serialized(kept), "filter_summary": summary}

    return search
