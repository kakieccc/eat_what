from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import now
from app.core.errors import AppError
from app.core.ids import lock_id, uid
from app.modules.choice.models import PlaceChoice
from app.modules.choice.schemas import ChoiceSnapshot
from app.modules.decision.models import (
    DecisionRun,
    DiscoverySession,
    PlaceCandidate,
)
from app.modules.decision.repository.mappers import place_from_candidate, request_for_run
from app.modules.decision.repository.transaction import DecisionTransaction
from app.modules.decision.schemas import DecisionIntent, DecisionRequest, DecisionRunResponse
from app.modules.decision.workflow.state import State
from app.modules.places.schemas import Place
from app.modules.task.errors import LostTaskLease
from app.modules.task.models import Task, TaskStatus, TaskStep
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

    async def read(self, run_id: str) -> DecisionRunResponse:
        return await self._read(run_id)

    async def read_for_user(self, user_id: str, run_id: str) -> DecisionRunResponse:
        return await self._read(run_id, user_id)

    async def _read(self, run_id: str, user_id: str | None = None) -> DecisionRunResponse:
        async with self.sessions.begin() as session:
            run = await self._run(session, run_id)
            discovery = await session.scalar(
                select(DiscoverySession).where(DiscoverySession.id == run.discovery_session_id)
                .with_for_update(read=True)
            )
            if discovery is None or (user_id is not None and discovery.user_id != user_id):
                raise AppError("NOT_FOUND", "发现会话不存在", 404)
            if discovery.current_run_id != run_id:
                raise AppError("RUN_SUPERSEDED", "请求冲突", 409)
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
            selected_candidate = (
                await session.get(PlaceCandidate, chosen.place_candidate_id) if chosen else None
            )
            warnings = []
            if run.filter_summary.get("searchFailures"):
                warnings.append("部分搜索暂不可用，候选餐厅可能不完整。")
            if run.filter_summary.get("detailFailures"):
                warnings.append("部分餐厅详情获取失败，已剔除并尝试补充其他餐厅。")
                if run.status == "completed" and len(candidates) < 3:
                    warnings.append(f"本次仅获得 {len(candidates)} 家有效推荐，可调整条件后重试。")
            return DecisionRunResponse(
                decision_run_id=run.id,
                discovery_session_id=run.discovery_session_id,
                status=run.status,
                request=request_for_run(run),
                places=[place_from_candidate(candidate) for candidate in candidates],
                intent=DecisionIntent.model_validate(run.intent),
                original_request=DecisionRequest.model_validate(run.original_request),
                filter_summary={key: count for key, count in run.filter_summary.items()},
                warnings=warnings,
                choice=ChoiceSnapshot(
                    id=chosen.id,
                    candidate_id=chosen.place_candidate_id,
                    decision_run_id=selected_candidate.decision_run_id,
                    selected_at=chosen.selected_at,
                )
                if chosen and selected_candidate
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
    async def transaction(self, user_id: str, lock_key: str) -> AsyncIterator[DecisionTransaction]:
        async with self.sessions.begin() as session:
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": lock_id(user_id + ":" + lock_key)},
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
                state = cast(State, dict(task.state))
                state["already_completed"] = True
                return task.id, run.id, task.request_id, state, run.duration_ms
            state = cast(State, dict(task.state))
            state.update({"task_id": task.id, "lease_token": claim.lease_token})
            run.status = "running"
            run.error_code = None
            run.completed_at = None
            task.phase = task.phase or "running"
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
        task = await session.scalar(
            select(Task)
            .where(
                Task.id == claim.task_id,
                Task.lease_token == claim.lease_token,
                Task.status == TaskStatus.running.value,
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
                *(Place.model_validate(raw).id for raw in state.get("places", [])),
            ]))
            self._persist_result(session, run, state)
            task.state = {key: value for key, value in state.items() if key != "lease_token"}
            task.status = TaskStatus.succeeded.value
            task.phase = "completed"
            task.lease_token = None
            task.lease_until = None
            task.completed_at = now()
            run.duration_ms += duration_ms
            run.status = "completed"
            run.completed_at = now()

    async def fail(self, claim: TaskClaim, code: str, message: str) -> bool:
        async with self.sessions.begin() as session:
            try:
                await self._current_session(session, claim)
            except LostTaskLease:
                return False
            task = await session.scalar(
                select(Task)
                .where(Task.id == claim.task_id, Task.lease_token == claim.lease_token)
                .with_for_update()
            )
            if task is None:
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
                run.status = "failed"
                run.error_code = code
                run.completed_at = now()
                return True
            return False

    def _persist_result(self, session: AsyncSession, run: DecisionRun, state: State) -> None:
        for rank, raw in enumerate(state.get("places", []), 1):
            place = Place.model_validate(raw).model_copy(
                update={"candidate_id": uid(), "rank": rank}
            )
            session.add(
                PlaceCandidate(
                    id=place.candidate_id,
                    decision_run_id=run.id,
                    place_key=place.id,
                    external_place_id=place.external_id,
                    name=place.name,
                    category_code=place.category_code,
                    category_name=place.category_name,
                    cuisine_types=place.cuisine_types,
                    tags=place.tags,
                    address=place.address,
                    latitude=place.location.latitude,
                    longitude=place.location.longitude,
                    straight_line_distance_meters=place.straight_line_distance_meters,
                    rating=place.rating,
                    average_cost=place.average_cost,
                    opening_hours_text=place.opening_hours_text,
                    phone=place.phone,
                    photos=place.photos,
                    score=place.score,
                    score_breakdown=place.score_breakdown,
                    rank=rank,
                    reason=place.reason,
                    warnings=place.warnings,
                    navigation_url=place.navigation_url,
                    place_snapshot=place.model_dump(mode="json"),
                )
            )
        run.effective_preferences = state["request"]
        run.filter_summary = dict(state.get("filter_summary", {}))
        run.llm_used = True
        run.status = "completed"
        run.completed_at = now()
