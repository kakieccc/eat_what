from __future__ import annotations

from app.core.errors import AppError
from app.core.ids import request_hash
from app.modules.decision.ports import DecisionRepository
from app.modules.decision.rules.refinement import apply_refinement
from app.modules.decision.schemas import DecisionCreateRequest, DecisionRequest, RefinementRequest
from app.modules.decision.workflow.state import SCHEMA_VERSION, State
from app.modules.places.schemas import Place
from app.modules.preferences.rules import require_allowed_food_limit
from app.modules.preferences.schemas import PrefillSnapshot


class DecisionCommandService:
    def __init__(self, repository: DecisionRepository) -> None:
        self.repository = repository

    async def create(
        self, user_id: str, request: DecisionCreateRequest, idempotency_key: str, request_id: str
    ) -> str:
        return await self._create(
            user_id, DecisionRequest.model_validate(request.model_dump(exclude={"prefill_snapshot"})),
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
        async with self.repository.transaction(user_id, endpoint + key) as tx:
            existing = await tx.idempotency(endpoint, key)
            if existing:
                if existing.request_hash != digest:
                    raise AppError("IDEMPOTENCY_CONFLICT", "请求冲突", 409)
                return str(existing.response_body["runId"])
        original = request
        if parent_id:
            parent_run = await self.repository.read_for_user(user_id, parent_id)
            if parent_run.choice is not None:
                raise AppError("SELECTION_COMPLETED", "本次选餐已结束，请开始新的选餐", 409)
            if parent_run.status != ("failed" if retry else "completed"):
                raise AppError("INVALID_STATE", "请求冲突", 409)
            request = parent_run.request
            if refinement:
                request = apply_refinement(request, refinement, [p.id for p in parent_run.places])
            original = parent_run.original_request
        assert request is not None and original is not None
        require_allowed_food_limit(request.preferences.allowed_foods)
        async with self.repository.transaction(user_id, endpoint + key) as tx:
            existing = await tx.idempotency(endpoint, key)
            if existing:
                if existing.request_hash != digest:
                    raise AppError("IDEMPOTENCY_CONFLICT", "请求冲突", 409)
                return str(existing.response_body["runId"])
            excluded: list[str] = []
            search_excluded: list[str] = []
            old_cuisines: list[str] = []
            if parent_id:
                parent = await tx.parent(parent_id)
                if parent.status != ("failed" if retry else "completed"):
                    raise AppError("INVALID_STATE", "请求冲突", 409)
                session_id = parent.session_id
                excluded = list(parent.excluded_place_keys)
                if refinement and refinement.action == "excludePlace":
                    excluded = list(dict.fromkeys([*excluded, refinement.value]))
                search_excluded = list(excluded)
                if refinement and refinement.action == "refresh":
                    search_excluded = list(
                        dict.fromkeys(excluded + await tx.seen_place_keys(session_id))
                    )
                old_cuisines = [
                    c for p in parent.place_snapshots for c in Place.model_validate(p).cuisine_types
                ]
            else:
                assert prefill is not None
                session_id = await tx.create_discovery(original, prefill)
            action: str = refinement.action if refinement else ""
            if retry:
                search_excluded = list(parent.retry_state.get("excluded", []))
                old_cuisines = list(parent.retry_state.get("old_cuisines", []))
                action = str(parent.retry_state.get("action", ""))
            run_id = await tx.create_run(session_id, request, parent_id, excluded, action, original)
            state: State = {
                "schema_version": SCHEMA_VERSION,
                "decision_run_id": run_id,
                "request": request.model_dump(mode="json"),
                "excluded": search_excluded,
                "action": action,
                "places": [],
                "filter_summary": {},
                "next_node": "search_places",
                "old_cuisines": old_cuisines,
                "recent": await tx.recent_place_keys(),
            }
            task_id = await tx.enqueue(
                run_id, "refinement" if parent_id else "decision", request_id, state
            )
            await tx.record_idempotency(endpoint, key, digest, run_id, task_id)
            return run_id
