from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from pydantic import TypeAdapter
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.decision.models import ConfirmationChange, DecisionRunResponse
from app.application.task.models import LostTaskLease, TaskClaim
from app.core.clock import now
from app.core.errors import AppError
from app.core.ids import lock_id, uid
from app.domain.places.models import Place
from app.infrastructure.persistence.decision_transaction import DecisionTransaction
from app.infrastructure.persistence.mappers import place_from_candidate, request_for_run
from app.infrastructure.persistence.models import (
    DecisionConfirmation,
    DecisionRun,
    DiscoverySession,
    PlaceCandidate,
    PlaceChoice,
    Task,
    TaskStatus,
    TaskStep,
)
from app.workflows.food_decision.state import State


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
        async with self.sessions() as session:
            run = await self._run(session, run_id)
            discovery = await session.get(DiscoverySession, run.discovery_session_id)
            if discovery is None or (user_id is not None and discovery.user_id != user_id):
                raise AppError("NOT_FOUND", "发现会话不存在", 404)
            candidates = list(
                (
                    await session.scalars(
                        select(PlaceCandidate)
                        .where(PlaceCandidate.decision_run_id == run.id)
                        .order_by(PlaceCandidate.rank)
                    )
                ).all()
            )
            confirmation = await session.scalar(
                select(DecisionConfirmation).where(
                    DecisionConfirmation.decision_run_id == run.id,
                    DecisionConfirmation.status == "pending",
                )
            )
            chosen = list(
                (
                    await session.scalars(
                        select(PlaceChoice.place_candidate_id).where(
                            PlaceChoice.discovery_session_id == run.discovery_session_id
                        )
                    )
                ).all()
            )
            task = await session.scalar(
                select(Task)
                .where(Task.decision_run_id == run.id)
                .order_by(Task.created_at.desc(), Task.id.desc())
            )
            status = (
                "awaitingConfirmation"
                if confirmation or (task and task.status == TaskStatus.waiting_confirmation.value)
                else run.status
            )
            return DecisionRunResponse(
                decision_run_id=run.id,
                discovery_session_id=run.discovery_session_id,
                status=status,
                request=request_for_run(run, discovery),
                places=[place_from_candidate(candidate) for candidate in candidates],
                confirmation=TypeAdapter(dict[str, ConfirmationChange]).validate_python(
                    confirmation.changes
                ) if confirmation else None,
                filter_summary=dict(run.filter_summary),
                chosen_candidate_ids=list(chosen),
                suggestions=[]
                if candidates
                else ["可以调整预算、步行上限或排除菜系后重新选择；系统不会自动放宽条件。"],
                error_code=run.error_code,
            )

    @asynccontextmanager
    async def transaction(
        self, user_id: str, lock_key: str
    ) -> AsyncIterator[DecisionTransaction]:
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

    async def _owned(self, session: AsyncSession, claim: TaskClaim) -> Task:
        task = await session.scalar(
            select(Task)
            .where(
                Task.id == claim.task_id,
                Task.lease_token == claim.lease_token,
                Task.status == TaskStatus.running.value,
            )
            .with_for_update()
        )
        if task is None:
            raise LostTaskLease("任务执行权已失效")
        return task

    async def wait_for_confirmation(self, claim: TaskClaim, state: State, duration_ms: int) -> None:
        async with self.sessions.begin() as session:
            task = await self._owned(session, claim)
            run = await session.get(DecisionRun, task.decision_run_id, with_for_update=True)
            if run is None:
                raise AppError("NOT_FOUND", "决策记录不存在", 404)
            confirmation = await session.scalar(
                select(DecisionConfirmation)
                .where(DecisionConfirmation.decision_run_id == run.id)
                .with_for_update()
            )
            changes = dict(state.get("changes", {}))
            if confirmation is None:
                session.add(
                    DecisionConfirmation(decision_run_id=run.id, changes=changes, status="pending")
                )
            else:
                confirmation.changes = changes
                confirmation.status = "pending"
                confirmation.resolved_at = None
            task.state = {key: value for key, value in state.items() if key != "lease_token"}
            task.status = TaskStatus.waiting_confirmation.value
            task.phase = "waiting_confirmation"
            task.lease_token = None
            task.lease_until = None
            run.duration_ms += duration_ms

    async def complete(self, claim: TaskClaim, state: State, run_id: str, duration_ms: int) -> None:
        async with self.sessions.begin() as session:
            task = await self._owned(session, claim)
            run = await session.get(DecisionRun, run_id, with_for_update=True)
            if run is None:
                raise AppError("NOT_FOUND", "决策记录不存在", 404)
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
                route = place.route.model_dump(mode="json") if place.route else None
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
                        address=place.address,
                        latitude=place.location.latitude,
                        longitude=place.location.longitude,
                        straight_line_distance_meters=place.straight_line_distance_meters,
                        walking_distance_meters=place.route.distance_meters
                        if place.route
                        else None,
                        walking_duration_seconds=place.route.duration_seconds
                        if place.route
                        else None,
                        rating=place.rating,
                        average_cost=place.average_cost,
                        business_status=place.business_status,
                        opening_hours_text=place.opening_hours_text,
                        phone=place.phone,
                        photos=place.photos,
                        score=place.score,
                        score_breakdown=place.score_breakdown,
                        rank=rank,
                        reason=place.reason,
                        warnings=place.warnings,
                        navigation_url=place.navigation_url,
                        route_snapshot=route,
                        place_snapshot=place.model_dump(mode="json"),
                    )
                )
            run.effective_preferences = state["request"]
            run.filter_summary = dict(state.get("filter_summary", {}))
            run.llm_used = bool(state.get("places"))
            run.status = "completed"
            run.completed_at = now()
