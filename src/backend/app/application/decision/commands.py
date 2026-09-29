from __future__ import annotations

from typing import cast

from app.application.decision.models import RefinementRequest
from app.application.decision.ports import DecisionRepository
from app.core.errors import AppError
from app.core.ids import request_hash
from app.domain.decision.models import DecisionRequest
from app.domain.decision.refinement import apply_refinement
from app.domain.places.models import Place
from app.workflows.food_decision.state import State


class DecisionCommandService:
    def __init__(self, repository: DecisionRepository) -> None:
        self.repository = repository

    async def create(
        self, user_id: str, request: DecisionRequest, idempotency_key: str, request_id: str
    ) -> str:
        return await self._create(user_id, request, idempotency_key, request_id)

    async def refine(
        self, user_id: str, parent_id: str, refinement: RefinementRequest,
        idempotency_key: str, request_id: str
    ) -> str:
        parent = await self.repository.read_for_user(user_id, parent_id)
        return await self._create(
            user_id, parent.request, idempotency_key, request_id,
            parent_id=parent_id, refinement=refinement
        )

    async def _create(
        self,
        user_id: str,
        request: DecisionRequest,
        key: str,
        request_id: str,
        parent_id: str | None = None,
        refinement: RefinementRequest | None = None,
    ) -> str:
        endpoint = f"decision-runs/{parent_id}/refinements" if parent_id else "decision-runs"
        raw = refinement.model_dump(mode="json") if refinement else request.model_dump(mode="json")
        digest = request_hash(raw)
        async with self.repository.transaction(user_id, endpoint + key) as tx:
            existing = await tx.idempotency(endpoint, key)
            if existing:
                if existing.request_hash != digest:
                    raise AppError("IDEMPOTENCY_CONFLICT", "同一请求标识对应不同内容", 409)
                return str(existing.response_body["runId"])
            excluded: list[str] = []
            action = ""
            old_cuisines: list[str] | None = None
            if parent_id:
                parent = await tx.parent(parent_id)
                if parent.status != "completed":
                    raise AppError("INVALID_STATE", "只能调整已完成的决策", 409)
                if refinement is None:
                    raise AppError("INVALID_REFINEMENT", "缺少调整动作")
                request = apply_refinement(parent.request, refinement, parent.previous_place_keys)
                excluded = list(
                    dict.fromkeys(parent.excluded_place_keys + parent.previous_place_keys)
                )
                action = refinement.action
                session_id = parent.session_id
                old_cuisines = [
                    cuisine
                    for snapshot in parent.place_snapshots
                    for cuisine in Place.model_validate(snapshot).cuisine_types
                ]
            else:
                session_id = await tx.create_discovery(request)
            run_id = await tx.create_run(session_id, request, parent_id, excluded, action)
            state: State = {
                "schema_version": 4,
                "decision_run_id": run_id,
                "request": request.model_dump(mode="json"),
                "excluded": excluded,
                "action": action,
                "places": [],
                "filter_summary": {},
                "awaiting_confirmation": False,
                "next_node": "parse_intent" if request.request_text else "search_places",
            }
            if old_cuisines is not None:
                state["old_cuisines"] = old_cuisines
            state["recent"] = await tx.recent_place_keys()
            task_id = await tx.enqueue(
                run_id, "refinement" if parent_id else "decision", request_id, state
            )
            await tx.record_idempotency(endpoint, key, digest, run_id, task_id)
            return run_id

    async def resume(
        self, user_id: str, run_id: str, accept_changes: bool | None,
        idempotency_key: str, request_id: str
    ) -> str:
        endpoint = f"decision-runs/{run_id}"
        digest = request_hash({"acceptChanges": accept_changes})
        async with self.repository.transaction(user_id, run_id + "resume") as tx:
            existing = await tx.idempotency(endpoint, idempotency_key)
            if existing:
                if existing.request_hash != digest:
                    raise AppError("IDEMPOTENCY_CONFLICT", "同一标识对应不同确认内容", 409)
                return str(existing.response_body.get("taskId", ""))
            snapshot = await tx.resume_snapshot(run_id)
            if snapshot.status == "failed":
                raise AppError("INVALID_STATE", "失败记录不可恢复，请重新推荐", 409)
            if snapshot.confirmation_pending and accept_changes is None:
                raise AppError("CONFIRMATION_REQUIRED", "请确认或拒绝建议的条件修改", 409)
            if snapshot.waiting_task_id is None or snapshot.waiting_state is None:
                raise AppError("INVALID_STATE", "当前记录不需要确认或已经恢复", 409)
            await tx.resolve_confirmation(run_id, accept_changes)
            continuation = cast(State, dict(snapshot.waiting_state))
            continuation.update(
                {
                    "confirmation_answer": accept_changes,
                    "awaiting_confirmation": False,
                    "next_node": "confirm_intent",
                }
            )
            await tx.supersede(snapshot.waiting_task_id)
            await tx.reset_run(run_id)
            task_id = await tx.enqueue(
                run_id, "resume", request_id, continuation, parent_task_id=snapshot.waiting_task_id
            )
            await tx.record_idempotency(endpoint, idempotency_key, digest, run_id, task_id)
            return task_id
