from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import now
from app.core.config import settings
from app.core.errors import AppError
from app.core.ids import lock_id, uid
from app.modules.choice.models import PlaceChoice
from app.modules.choice.schemas import ChoiceSnapshot
from app.modules.decision.models import (
    DecisionRun,
    DiscoverySession,
    PlaceCandidate,
)
from app.modules.decision.ports import RunStreamStatus
from app.modules.decision.repository.mappers import place_from_candidate, request_for_run
from app.modules.decision.repository.transaction import DecisionTransaction
from app.modules.decision.schemas import DecisionRequest, DecisionRunResponse
from app.modules.decision.workflow.events import RunFailed, WorkflowError
from app.modules.decision.workflow.state import SCHEMA_VERSION, STATE_ADAPTER, State
from app.modules.task.errors import LostTaskLease
from app.modules.task.models import Task, TaskStatus, TaskStep
from app.modules.task.repository import record_event
from app.modules.task.types import TaskClaim


class DecisionRepository:
    """Database transactions and mapping for decision use cases."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], model_name: str) -> None:
        self.sessions = sessions
        self.model_name = model_name

    async def _run(self, session: AsyncSession, run_id: str, lock: bool = False) -> DecisionRun:
        statement = select(DecisionRun).where(DecisionRun.id == run_id)
        if lock:
            statement = statement.with_for_update()
        run = await session.scalar(statement)
        if run is None:
            raise AppError("NOT_FOUND", "记录不存在", 404)
        return run

    async def stream_status(self, user_id: str, run_id: str) -> RunStreamStatus:
        latest_task = select(Task.id).where(Task.decision_run_id == DecisionRun.id).order_by(
            Task.created_at.desc(), Task.id.desc(),
        ).limit(1).correlate(DecisionRun).scalar_subquery()
        async with self.sessions() as session:
            row = (await session.execute(select(
                DecisionRun.status, DecisionRun.error_code, DiscoverySession.current_run_id,
                latest_task, DecisionRun.workflow_version,
            ).join(DiscoverySession, DecisionRun.discovery_session_id == DiscoverySession.id).where(
                DecisionRun.id == run_id, DiscoverySession.user_id == user_id,
            ))).one_or_none()
        if row is None:
            raise AppError("NOT_FOUND", "记录不存在", 404)
        status, error_code, current_run, task_id, version = row
        if current_run != run_id:
            raise AppError("RUN_SUPERSEDED", "请求冲突", 409)
        if version != str(SCHEMA_VERSION):
            raise AppError("WORKFLOW_UPGRADED", "选餐流程已更新，请开始新的选餐", 409)
        return RunStreamStatus(status=status, error_code=error_code, task_id=task_id)

    async def read_for_user(self, user_id: str, run_id: str) -> DecisionRunResponse:
        async with self.sessions.begin() as session:
            run = await self._run(session, run_id)
            discovery = await session.scalar(
                select(DiscoverySession).where(DiscoverySession.id == run.discovery_session_id)
                .with_for_update(read=True)
            )
            if discovery is None or discovery.user_id != user_id:
                raise AppError("NOT_FOUND", "发现会话不存在", 404)
            if discovery.current_run_id != run_id:
                raise AppError("RUN_SUPERSEDED", "请求冲突", 409)
            if run.workflow_version != str(SCHEMA_VERSION):
                raise AppError("WORKFLOW_UPGRADED", "选餐流程已更新，请开始新的选餐", 409)
            candidates = list(
                (
                    await session.scalars(
                        select(PlaceCandidate)
                        .where(PlaceCandidate.decision_run_id == run.id)
                        .order_by(PlaceCandidate.rank)
                    )
                ).all()
            )
            chosen = await session.scalar(
                select(PlaceChoice).where(
                    PlaceChoice.discovery_session_id == run.discovery_session_id
                )
            )
            warnings = []
            if run.filter_summary.get("searchFailures"):
                warnings.append("部分搜索暂不可用，候选餐厅可能不完整。")
            if run.filter_summary.get("detailFailures"):
                warnings.append("部分餐厅详情获取失败，已剔除并尝试补充其他餐厅。")
                if run.status == "completed" and len(candidates) < settings.decision_recommendation_limit:
                    warnings.append(f"本次仅获得 {len(candidates)} 家有效推荐，可调整条件后重试。")
            return DecisionRunResponse(
                decision_run_id=run.id,
                discovery_session_id=run.discovery_session_id,
                status=run.status,
                request=request_for_run(run),
                places=[place_from_candidate(candidate) for candidate in candidates],
                original_request=DecisionRequest.model_validate(run.original_request),
                filter_summary={key: count for key, count in run.filter_summary.items()},
                warnings=warnings,
                choice=ChoiceSnapshot(
                    id=chosen.id,
                    candidate_id=chosen.place_candidate_id,
                    decision_run_id=run.id,
                    selected_at=chosen.selected_at,
                )
                if chosen
                else None,
                suggestions=[]
                if candidates or run.status != "completed"
                else (
                    ["本次检索达到查询上限，尚未找到合适餐厅。"]
                    if run.filter_summary.get("searchBudgetExhausted")
                    else ["当前范围和条件下暂未找到合适餐厅。"]
                )
                + ["可以修改预算、范围或食物条件后重试。"],
                error_code=run.error_code,
            )

    @asynccontextmanager
    async def transaction(self, user_id: str) -> AsyncIterator[DecisionTransaction]:
        async with self.sessions.begin() as session:
            # Different idempotency keys still compete for the same user's single task slot.
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": lock_id("decision-tasks:" + user_id)},
            )
            yield DecisionTransaction(session, self.model_name, user_id)

    async def prepare(self, claim: TaskClaim) -> tuple[str, str, str, State, int]:
        async with self.sessions.begin() as session:
            task = await self._owned(session, claim)
            run = await session.get(DecisionRun, task.decision_run_id, with_for_update=True)
            if run is None:
                raise AppError("NOT_FOUND", "决策记录不存在", 404)
            if run.status == "completed":
                task.status = TaskStatus.succeeded.value
                task.lease_token = None
                task.lease_until = None
                return task.id, run.id, task.request_id, {"already_completed": True}, run.duration_ms
            if task.state.get("schema_version") != SCHEMA_VERSION:
                raise AppError("WORKFLOW_UPGRADED", "任务版本已更新，请重新推荐", 409)
            state = STATE_ADAPTER.validate_python(task.state)
            state.update({"task_id": task.id, "lease_token": claim.lease_token})
            run.status = "running"
            run.error_code = None
            run.completed_at = None
            task.phase = task.phase or "running"
            run.duration_ms = task.elapsed_ms()
            return task.id, run.id, task.request_id, state, run.duration_ms

    async def _current_session(self, session: AsyncSession, claim: TaskClaim) -> DiscoverySession:
        task = await session.get(Task, claim.task_id)
        run = await session.get(DecisionRun, task.decision_run_id) if task else None
        discovery = await session.scalar(
            select(DiscoverySession).where(DiscoverySession.id == run.discovery_session_id)
            .with_for_update()
        ) if run else None
        if discovery is None or run is None or discovery.current_run_id != run.id:
            raise LostTaskLease("任务已被替代")
        return cast(DiscoverySession, discovery)

    async def _owned(self, session: AsyncSession, claim: TaskClaim) -> Task:
        await self._current_session(session, claim)
        # Waiting for the discovery lock may leave the already loaded Task stale.
        task = await session.scalar(
            select(Task)
            .where(
                Task.id == claim.task_id,
                Task.lease_token == claim.lease_token,
                Task.status == TaskStatus.running.value,
                Task.lease_until > now(),
            )
            .with_for_update().execution_options(populate_existing=True)
        )
        if task is None:
            raise LostTaskLease("任务执行权已失效")
        return task

    async def complete(self, claim: TaskClaim, state: State, run_id: str, duration_ms: int) -> None:
        async with self.sessions.begin() as session:
            task = await self._owned(session, claim)
            run = await session.get(DecisionRun, run_id, with_for_update=True)
            if run is None:
                raise AppError("NOT_FOUND", "决策记录不存在", 404)
            discovery = await session.get(DiscoverySession, run.discovery_session_id)
            assert discovery is not None
            discovery.seen_place_keys = list(dict.fromkeys([
                *discovery.seen_place_keys,
                *(place.id for place in state["places"]),
            ]))
            self._persist_result(session, run, state)
            task.status = TaskStatus.succeeded.value
            task.phase = "completed"
            task.lease_token = None
            task.lease_until = None
            task.completed_at = now()
            run.duration_ms = max(run.duration_ms, duration_ms, task.elapsed_ms())
            run.status = "completed"
            run.completed_at = now()

    async def fail(self, claim: TaskClaim, code: str, message: str, retryable: bool) -> bool:
        async with self.sessions.begin() as session:
            try:
                task = await self._owned(session, claim)
            except LostTaskLease:
                return False
            task.status = TaskStatus.failed.value
            task.phase = "failed"
            task.error_code = code
            task.error_message = message
            task.lease_token = None
            task.lease_until = None
            task.completed_at = now()
            step = await session.scalar(
                select(TaskStep)
                .where(TaskStep.task_id == task.id, TaskStep.status == "running")
                .order_by(TaskStep.ordinal.desc())
                .limit(1)
                .with_for_update()
            )
            if step is not None:
                step.status = "failed"
                step.error_code = code
                step.error_message = message[:500]
                step.completed_at = now()
            run = await session.get(DecisionRun, task.decision_run_id, with_for_update=True)
            if run is not None and run.status != "completed":
                run.duration_ms = max(run.duration_ms, task.elapsed_ms())
                run.status = "failed"
                run.error_code = code
                run.completed_at = now()
                await record_event(session, task.id, RunFailed(error=WorkflowError(
                    code=code, message=message, retryable=retryable,
                )))
                return True
            return False

    def _persist_result(self, session: AsyncSession, run: DecisionRun, state: State) -> None:
        for rank, candidate in enumerate(state["places"], 1):
            place = candidate.model_copy(
                update={"candidate_id": uid(), "rank": rank}
            )
            session.add(
                PlaceCandidate(
                    id=place.candidate_id,
                    decision_run_id=run.id,
                    place_key=place.id,
                    rank=rank,
                    place_snapshot=place.model_dump(mode="json"),
                )
            )
        run.effective_preferences = state["request"].model_dump(mode="json")
        run.filter_summary = dict(state["filter_summary"])
        run.llm_used = True
        run.status = "completed"
        run.completed_at = now()
