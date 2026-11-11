from __future__ import annotations

from app.core.errors import AppError
from app.core.ids import request_hash
from app.modules.decision.ports import DecisionRepository
from app.modules.decision.rules.refinement import apply_refinement
from app.modules.decision.schemas import DecisionCreateRequest, DecisionRequest, RefinementRequest
from app.modules.decision.workflow.state import SCHEMA_VERSION, State
from app.modules.preferences.schemas import PrefillSnapshot


class DecisionCommandService:
    def __init__(
        self, repository: DecisionRepository, max_active: int = 16, submissions_per_minute: int = 5,
    ) -> None:
        self.repository = repository
        self.max_active = max_active
        self.submissions_per_minute = submissions_per_minute

    async def create(
        self, user_id: str, request: DecisionCreateRequest, idempotency_key: str, request_id: str
    ) -> str:
        return await self._create(
            user_id, DecisionRequest.model_construct(
                origin=request.origin, preferences=request.preferences,
                meal_period=request.meal_period, party_size=request.party_size,
                request_text=request.request_text,
            ),
            idempotency_key, request_id, prefill=request.prefill_snapshot,
        )

    async def refine(
        self,
        user_id: str,
        parent_id: str,
        refinement: RefinementRequest,
        idempotency_key: str,
        request_id: str,
    ) -> str:
        return await self._create(
            user_id, None, idempotency_key, request_id, parent_id, refinement
        )

    async def retry(self, user_id: str, run_id: str, key: str, request_id: str) -> str:
        return await self._create(user_id, None, key, request_id, run_id, retry=True)

    async def _create(
        self,
        user_id: str,
        request: DecisionRequest | None,
        key: str,
        request_id: str,
        parent_id: str | None = None,
        refinement: RefinementRequest | None = None,
        retry: bool = False,
        prefill: PrefillSnapshot | None = None,
    ) -> str:
        endpoint = (
            f"decision-runs/{parent_id}/{'retry' if retry else 'refinements'}"
            if parent_id else "decision-runs"
        )
        digest = request_hash(
            refinement.model_dump(mode="json") if refinement
            else {"request": request.model_dump(mode="json"),
                  "prefill": prefill.model_dump(mode="json") if prefill else None} if request else {}
        )
        async with self.repository.transaction(user_id) as tx:
            # Hold the user lock through replay lookup, parent reads, and task creation.
            existing = await tx.idempotency(endpoint, key)
            if existing:
                if existing.request_hash != digest:
                    raise AppError("IDEMPOTENCY_CONFLICT", "请求冲突", 409)
                return str(existing.response_body["runId"])
            original = request
            excluded: list[str] = []
            search_excluded: list[str] = []
            old_cuisines: list[str] = []
            action: str = refinement.action if refinement else ""
            if parent_id:
                parent = await tx.parent(parent_id)
                if parent.has_choice:
                    raise AppError("SELECTION_COMPLETED", "本次选餐已结束，请开始新的选餐", 409)
                if parent.status != ("failed" if retry else "completed"):
                    raise AppError("INVALID_STATE", "请求冲突", 409)
                parent_places = parent.places
                request = parent.request
                if refinement:
                    request = apply_refinement(request, refinement, [p.id for p in parent_places])
                original = parent.original_request
                session_id = parent.session_id
                excluded = list(parent.excluded_place_keys)
                if refinement and refinement.action == "excludePlace":
                    excluded = list(dict.fromkeys([*excluded, refinement.value]))
                search_excluded = list(excluded)
                if refinement and refinement.action == "refresh":
                    search_excluded = list(
                        dict.fromkeys(excluded + await tx.seen_place_keys(session_id))
                    )
                old_cuisines = [c for p in parent_places for c in p.cuisine_types]
                if retry:
                    # Replay the failed run's search intent, including refresh exclusions.
                    search_excluded = list(parent.retry_state["excluded"])
                    old_cuisines = list(parent.retry_state["old_cuisines"])
                    action = parent.retry_state["action"]
            assert request is not None and original is not None
            await tx.require_task_capacity(self.max_active, self.submissions_per_minute)
            if not parent_id:
                assert prefill is not None
                session_id = await tx.create_discovery(original, prefill)
            run_id = await tx.create_run(session_id, request, parent_id, excluded, action, original)
            state: State = {
                "schema_version": SCHEMA_VERSION,
                "decision_run_id": run_id,
                "request": request,
                "excluded": search_excluded,
                "action": action,
                "places": [],
                "filter_summary": {},
                "old_cuisines": old_cuisines,
                "recent": await tx.recent_place_keys(),
            }
            task_id = await tx.enqueue(run_id, request_id, state)
            await tx.record_idempotency(endpoint, key, digest, run_id, task_id)
            return run_id
