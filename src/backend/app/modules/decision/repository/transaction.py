from __future__ import annotations

from datetime import timedelta
from typing import cast

from sqlalchemy import String, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now
from app.core.errors import AppError
from app.modules.choice.models import PlaceChoice
from app.modules.decision.models import (
    DecisionRun,
    DiscoverySession,
    IdempotencyRecord,
    PlaceCandidate,
)
from app.modules.decision.ports import IdempotencySnapshot, ParentSnapshot
from app.modules.decision.repository.mappers import request_for_run, session_values
from app.modules.decision.schemas import DecisionIntent, DecisionRequest
from app.modules.decision.workflow.state import SCHEMA_VERSION, State
from app.modules.task.models import Task, TaskEvent, TaskStatus


class DecisionTransaction:
    def __init__(self, session: AsyncSession, model_name: str, user_id: str) -> None:
        self.session = session
        self.model_name = model_name
        self.user_id = user_id

    async def idempotency(self, endpoint: str, key: str) -> IdempotencySnapshot | None:
        row = await self.session.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.user_id == self.user_id,
                IdempotencyRecord.endpoint == endpoint,
                IdempotencyRecord.idempotency_key == key,
            )
        )
        if row and "runId" in row.response_body:
            await self._run(str(row.response_body["runId"]))
        return IdempotencySnapshot(row.request_hash, dict(row.response_body)) if row else None

    async def record_idempotency(
        self, endpoint: str, key: str, digest: str, run_id: str, task_id: str
    ) -> None:
        self.session.add(
            IdempotencyRecord(
                user_id=self.user_id,
                endpoint=endpoint,
                idempotency_key=key,
                request_hash=digest,
                response_body={"runId": run_id, "taskId": task_id},
                expires_at=now() + timedelta(days=7),
            )
        )

    async def _run(self, run_id: str) -> DecisionRun:
        run = await self.session.get(DecisionRun, run_id)
        if run is None:
            raise AppError("NOT_FOUND", "记录不存在", 404)
        discovery = await self.session.scalar(
            select(DiscoverySession).where(
                DiscoverySession.id == run.discovery_session_id,
                DiscoverySession.user_id == self.user_id,
            ).with_for_update()
        )
        if discovery is None:
            raise AppError("NOT_FOUND", "记录不存在", 404)
        if discovery.current_run_id != run_id:
            raise AppError("RUN_SUPERSEDED", "请求冲突", 409)
        await self.session.refresh(run, with_for_update=True)
        return run

    async def parent(self, run_id: str) -> ParentSnapshot:
        run = await self._run(run_id)
        discovery = await self.session.get(DiscoverySession, run.discovery_session_id)
        if discovery is None:
            raise AppError("NOT_FOUND", "发现会话不存在", 404)
        candidates = list(
            (
                await self.session.scalars(
                    select(PlaceCandidate).where(PlaceCandidate.decision_run_id == run.id)
                )
            ).all()
        )
        return ParentSnapshot(
            status=run.status,
            session_id=discovery.id,
            request=request_for_run(run, discovery),
            excluded_place_keys=list(run.excluded_place_keys),
            previous_place_keys=[candidate.place_key for candidate in candidates],
            place_snapshots=[dict(candidate.place_snapshot) for candidate in candidates],
            retry_state=cast(State, dict((await self.session.scalar(
                select(Task.state).where(Task.decision_run_id == run.id)
                .order_by(Task.created_at.desc(), Task.id.desc()).limit(1)
            )) or {})),
        )

    async def create_discovery(self, request: DecisionRequest) -> str:
        discovery = DiscoverySession(user_id=self.user_id, **session_values(request))
        self.session.add(discovery)
        await self.session.flush()
        return discovery.id

    async def create_run(
        self,
        session_id: str,
        request: DecisionRequest,
        parent_id: str | None,
        excluded: list[str],
        action: str,
    ) -> str:
        run = DecisionRun(
            discovery_session_id=session_id,
            parent_decision_id=parent_id,
            workflow_version=str(SCHEMA_VERSION),
            effective_preferences=request.model_dump(mode="json"),
            excluded_place_keys=excluded,
            refinement_action=action,
            model_name=self.model_name,
        )
        self.session.add(run)
        await self.session.flush()
        discovery = await self.session.get(DiscoverySession, session_id, with_for_update=True)
        if discovery is None:
            raise AppError("NOT_FOUND", "记录不存在", 404)
        if parent_id:
            if discovery.current_run_id != parent_id:
                raise AppError("RUN_SUPERSEDED", "请求冲突", 409)
            await self._discard_results(parent_id, session_id)
        discovery.current_run_id = run.id
        await self.session.flush()
        return run.id

    async def recent_place_keys(self) -> list[str]:
        return list(
            (
                await self.session.scalars(
                    select(PlaceCandidate.place_key)
                    .join(PlaceChoice, PlaceChoice.place_candidate_id == PlaceCandidate.id)
                    .where(PlaceChoice.user_id == self.user_id)
                    .order_by(PlaceChoice.selected_at.desc())
                    .limit(20)
                )
            ).all()
        )

    async def enqueue(
        self,
        run_id: str,
        kind: str,
        request_id: str,
        state: State,
        parent_task_id: str | None = None,
    ) -> str:
        task = Task(
            decision_run_id=run_id,
            parent_task_id=parent_task_id,
            kind=kind,
            status=TaskStatus.queued.value,
            phase="queued",
            request_id=request_id,
            state=dict(state),
        )
        self.session.add(task)
        await self.session.flush()
        state["task_id"] = task.id
        task.state = dict(state)
        return task.id

    async def seen_place_keys(self, session_id: str) -> list[str]:
        discovery = await self.session.get(DiscoverySession, session_id)
        return list(discovery.seen_place_keys) if discovery else []

    async def _discard_results(self, run_id: str, session_id: str) -> None:
        candidate_ids = select(PlaceCandidate.id.cast(String)).where(PlaceCandidate.decision_run_id == run_id)
        await self.session.execute(
            update(IdempotencyRecord).where(
                IdempotencyRecord.user_id == self.user_id,
                IdempotencyRecord.endpoint == "place-choices",
                IdempotencyRecord.response_body["candidateId"].astext.in_(candidate_ids),
            ).values(response_body={"superseded": True})
        )
        await self.session.execute(delete(PlaceChoice).where(PlaceChoice.discovery_session_id == session_id))
        await self.session.execute(delete(PlaceCandidate).where(PlaceCandidate.decision_run_id == run_id))
        task_ids = select(Task.id).where(Task.decision_run_id == run_id)
        # Revoke leases before removing checkpoints/events; late workers cannot repopulate them.
        await self.session.execute(update(Task).where(Task.decision_run_id == run_id).values(
            status=TaskStatus.superseded.value, state={}, lease_token=None, lease_until=None,
            error_message=None,
        ))
        await self.session.execute(delete(TaskEvent).where(TaskEvent.task_id.in_(task_ids)))
        await self.session.execute(update(DecisionRun).where(DecisionRun.id == run_id).values(
            original_request={}, intent={}, effective_preferences={}, filter_summary={},
            excluded_place_keys=[],
        ))

    async def set_intent(
        self, run_id: str, original: DecisionRequest, intent: DecisionIntent, duration_ms: int
    ) -> None:
        run = await self._run(run_id)
        run.original_request = original.model_dump(mode="json")
        run.intent = intent.model_dump(mode="json")
        run.duration_ms = duration_ms
        run.llm_used = True
