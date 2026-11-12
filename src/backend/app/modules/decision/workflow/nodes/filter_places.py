import json
import logging
import time
from collections.abc import Awaitable, Callable

from app.core.config import settings
from app.modules.decision.ports import FoodDecisionLlm
from app.modules.decision.rules.policies import score_places
from app.modules.decision.workflow.nodes.search_places import build as build_search
from app.modules.decision.workflow.state import State
from app.modules.places.schemas import Place
from app.modules.places.service import PlaceService

log = logging.getLogger("food.decision")


def build(service: PlaceService, llm: FoodDecisionLlm) -> Callable[[State], Awaitable[State]]:
    search_more = build_search(service)

    async def filtering(state: State) -> State:
        request = state["request"]

        def ranked(candidates: list[Place]) -> list[Place]:
            return score_places(
                candidates, request, state["action"], state["recent"],
            )

        current = state.copy()
        pending = ranked(state["places"])
        checked: set[str] = set()
        kept: list[Place] = []
        summary = dict(state["filter_summary"])
        for batch_number in range(1, 3):
            if len(kept) >= settings.decision_recommendation_limit:
                break
            if not pending:
                more = await search_more({
                    **current, "places": kept, "filter_summary": summary,
                })
                current.update(more)
                summary = more["filter_summary"]
                pending = ranked([p for p in more["places"] if p.id not in checked])
                if not pending:
                    break
            batch_size = settings.decision_candidate_limit
            batch, pending = pending[:batch_size], pending[batch_size:]
            checked.update(p.id for p in batch)
            started = time.monotonic()
            food_valid = await llm.filter_foods(batch, request)
            log.info(json.dumps({
                "event": "foodFilterBatch",
                "taskId": state["task_id"],
                "batch": batch_number,
                "inputCount": len(batch),
                "acceptedCount": len(food_valid),
                "durationMs": int((time.monotonic() - started) * 1000),
            }))
            kept.extend(food_valid)
            summary["foodRequirements"] = summary.get("foodRequirements", 0) + len(batch) - len(food_valid)
        return {
            **current,
            "places": ranked(kept)[:settings.decision_candidate_limit],
            "filter_summary": summary,
        }

    return filtering
