from __future__ import annotations

from datetime import timedelta
from math import ceil

from sqlalchemy import String, delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now
from app.core.errors import AppError
from app.core.ids import lock_id
from app.modules.choice.models import PlaceChoice
from app.modules.decision.models import (
    DecisionRun,
    DiscoverySession,
    IdempotencyRecord,
    PlaceCandidate,
)
from app.modules.decision.ports import IdempotencySnapshot, ParentSnapshot
from app.modules.decision.repository.mappers import place_from_candidate
from app.modules.decision.schemas import DecisionRequest
from app.modules.decision.workflow.state import SCHEMA_VERSION, STATE_ADAPTER, State
from app.modules.preferences.schemas import PrefillSnapshot
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
        current = now()
        if row and row.expires_at <= current:
            await self.session.execute(delete(IdempotencyRecord).where(
                IdempotencyRecord.id == row.id, IdempotencyRecord.expires_at <= current,
            ))
            await self.session.flush()
            return None
        if row:
            await self._run(str(row.response_body["runId"]))
        return IdempotencySnapshot(row.request_hash, dict(row.response_body)) if row else None

    async def require_task_capacity(self, max_active: int, submissions_per_minute: int) -> None:
        active = await self.session.scalar(
            select(Task.id)
            .join(DecisionRun, Task.decision_run_id == DecisionRun.id)
            .join(DiscoverySession, DecisionRun.discovery_session_id == DiscoverySession.id)
            .where(
                DiscoverySession.user_id == self.user_id,
                Task.status.in_((TaskStatus.queued.value, TaskStatus.running.value)),
            ).limit(1)
        )
        if active is not None:
            raise AppError(
                "USER_TASK_LIMIT_REACHED", "已有推荐任务排队或执行中，请等待完成后再试", 429, True,
            )
        current = now()
        recent = await self.session.scalar(
            select(Task.created_at)
            .join(DecisionRun, Task.decision_run_id == DecisionRun.id)
            .join(DiscoverySession, DecisionRun.discovery_session_id == DiscoverySession.id)
            .where(
                DiscoverySession.user_id == self.user_id,
                Task.created_at > current - timedelta(seconds=60),
            ).order_by(Task.created_at.desc()).offset(submissions_per_minute - 1).limit(1)
        )
        if recent is not None:
            retry_after = max(1, ceil((recent + timedelta(seconds=60) - current).total_seconds()))
            raise AppError(
                "USER_TASK_RATE_LIMITED", f"每 60 秒最多提交 {submissions_per_minute} 次推荐，请一分钟后再试", 429, True,
                retry_after=retry_after,
            )
        # Hold the admission lock until task creation commits, across all users and processes.
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id("decision-tasks:admission")},
        )
        full = await self.session.scalar(
            select(Task.id).where(Task.status.in_((TaskStatus.queued.value, TaskStatus.running.value)))
            .offset(max_active - 1).limit(1)
        )
        if full is not None:
            raise AppError(
                "QUEUE_FULL", "当前推荐任务已满，任务未受理，请稍后重试", 503, True, retry_after=10,
            )

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
        if run.workflow_version != str(SCHEMA_VERSION):
            raise AppError("WORKFLOW_UPGRADED", "选餐流程已更新，请开始新的选餐", 409)
        return run

    async def parent(self, run_id: str) -> ParentSnapshot:
        run = await self._run(run_id)
        candidates = list(
            (
                await self.session.scalars(
                    select(PlaceCandidate).where(PlaceCandidate.decision_run_id == run.id)
                )
            ).all()
        )
        return ParentSnapshot(
            status=run.status,
            session_id=run.discovery_session_id,
            request=DecisionRequest.model_validate(run.effective_preferences),
            original_request=DecisionRequest.model_validate(run.original_request),
            has_choice=await self.session.scalar(
                select(PlaceChoice.id).where(
                    PlaceChoice.discovery_session_id == run.discovery_session_id,
                )
            ) is not None,
            excluded_place_keys=list(run.excluded_place_keys),
            places=[place_from_candidate(candidate) for candidate in candidates],
            retry_state=STATE_ADAPTER.validate_python((await self.session.execute(
                select(Task.state).where(Task.decision_run_id == run.id)
                .order_by(Task.created_at.desc(), Task.id.desc()).limit(1)
            )).scalar_one()),
        )

    async def create_discovery(self, request: DecisionRequest, prefill: PrefillSnapshot) -> str:
        discovery = DiscoverySession(
            user_id=self.user_id, prefill_snapshot=prefill.model_dump(mode="json"),
            request_snapshot=request.model_dump(mode="json"),
        )
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
        original: DecisionRequest,
    ) -> str:
        run = DecisionRun(
            discovery_session_id=session_id,
            parent_decision_id=parent_id,
            workflow_version=str(SCHEMA_VERSION),
            original_request=original.model_dump(mode="json"),
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
        request_id: str,
        state: State,
    ) -> str:
        task = Task(
            decision_run_id=run_id,
            status=TaskStatus.queued.value,
            phase="queued",
            request_id=request_id,
            state=STATE_ADAPTER.dump_python(state, mode="json"),
        )
        self.session.add(task)
        await self.session.flush()
        state["task_id"] = task.id
        task.state = STATE_ADAPTER.dump_python(state, mode="json")
        return task.id

    async def seen_place_keys(self, session_id: str) -> list[str]:
        discovery = await self.session.get(DiscoverySession, session_id)
        assert discovery is not None
        return list(discovery.seen_place_keys)

    async def _discard_results(self, run_id: str, session_id: str) -> None:
        if await self.session.scalar(
            select(PlaceChoice.id).where(PlaceChoice.discovery_session_id == session_id)
        ):
            raise AppError("SELECTION_COMPLETED", "本次选餐已结束，请开始新的选餐", 409)
        candidate_ids = select(PlaceCandidate.id.cast(String)).where(PlaceCandidate.decision_run_id == run_id)
        await self.session.execute(
            update(IdempotencyRecord).where(
                IdempotencyRecord.user_id == self.user_id,
                IdempotencyRecord.endpoint == "place-choices",
                IdempotencyRecord.response_body["candidateId"].astext.in_(candidate_ids),
            ).values(response_body={"superseded": True})
        )
        await self.session.execute(delete(PlaceCandidate).where(PlaceCandidate.decision_run_id == run_id))
        task_ids = select(Task.id).where(Task.decision_run_id == run_id)
        # Revoke leases before removing task input/events; late workers cannot repopulate them.
        await self.session.execute(update(Task).where(Task.decision_run_id == run_id).values(
            status=TaskStatus.superseded.value, state={}, lease_token=None, lease_until=None,
            error_message=None,
        ))
        await self.session.execute(delete(TaskEvent).where(TaskEvent.task_id.in_(task_ids)))
        await self.session.execute(update(DecisionRun).where(DecisionRun.id == run_id).values(
            original_request={}, effective_preferences={}, filter_summary={},
            excluded_place_keys=[],
        ))
