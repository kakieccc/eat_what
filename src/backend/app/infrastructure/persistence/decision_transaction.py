from __future__ import annotations

from datetime import timedelta
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.decision.ports import IdempotencySnapshot, ParentSnapshot, ResumeSnapshot
from app.core.clock import now
from app.core.errors import AppError
from app.domain.decision.models import DecisionRequest
from app.infrastructure.persistence.mappers import request_for_run, session_values
from app.infrastructure.persistence.models import (
    DecisionConfirmation,
    DecisionRun,
    DiscoverySession,
    IdempotencyRecord,
    PlaceCandidate,
    PlaceChoice,
    Task,
    TaskStatus,
)
from app.workflows.food_decision.state import State


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
        run = await self.session.scalar(
            select(DecisionRun)
            .join(DiscoverySession, DecisionRun.discovery_session_id == DiscoverySession.id)
            .where(DecisionRun.id == run_id, DiscoverySession.user_id == self.user_id)
            .with_for_update(of=DecisionRun)
        )
        if run is None:
            raise AppError("NOT_FOUND", "记录不存在", 404)
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
            workflow_version="4",
            effective_preferences=request.model_dump(mode="json"),
            excluded_place_keys=excluded,
            refinement_action=action,
            model_name=self.model_name,
        )
        self.session.add(run)
        await self.session.flush()
        return run.id

    async def recent_place_keys(self) -> list[str]:
        return list(
            (
                await self.session.scalars(
                    select(PlaceCandidate.place_key)
                    .join(PlaceChoice, PlaceChoice.place_candidate_id == PlaceCandidate.id)
                    .where(PlaceChoice.user_id == self.user_id)
                    .order_by(PlaceChoice.created_at.desc())
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

    async def resume_snapshot(self, run_id: str) -> ResumeSnapshot:
        run = await self._run(run_id)
        confirmation = await self.session.scalar(
            select(DecisionConfirmation)
            .where(
                DecisionConfirmation.decision_run_id == run_id,
                DecisionConfirmation.status == "pending",
            )
            .with_for_update()
        )
        waiting = await self.session.scalar(
            select(Task)
            .where(
                Task.decision_run_id == run_id,
                Task.status == TaskStatus.waiting_confirmation.value,
            )
            .order_by(Task.created_at.desc(), Task.id.desc())
            .with_for_update()
        )
        return ResumeSnapshot(
            status=run.status,
            confirmation_pending=confirmation is not None,
            waiting_task_id=waiting.id if waiting else None,
            waiting_state=cast(State, dict(waiting.state)) if waiting else None,
        )

    async def resolve_confirmation(self, run_id: str, accepted: bool | None) -> None:
        confirmation = await self.session.scalar(
            select(DecisionConfirmation)
            .where(
                DecisionConfirmation.decision_run_id == run_id,
                DecisionConfirmation.status == "pending",
            )
            .with_for_update()
        )
        if confirmation is not None:
            confirmation.status = "accepted" if accepted else "rejected"
            confirmation.resolved_at = now()

    async def supersede(self, task_id: str) -> None:
        task = await self.session.get(Task, task_id, with_for_update=True)
        if task is None:
            raise AppError("INVALID_STATE", "当前记录不需要确认或已经恢复", 409)
        task.status = TaskStatus.superseded.value
        task.phase = "superseded"
        task.completed_at = now()

    async def reset_run(self, run_id: str) -> None:
        run = await self._run(run_id)
        run.status = "pending"
        run.error_code = None
        run.completed_at = None
