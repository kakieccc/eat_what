from __future__ import annotations

import asyncio
import logging
import secrets
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any, cast

from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.task.models import EventRecord, LostTaskLease, TaskClaim, TaskSnapshot
from app.core.clock import now
from app.infrastructure.persistence.models.task import Task, TaskEvent, TaskStatus, TaskStep

log = logging.getLogger("food.task")


def json_payload(value: BaseModel | dict[str, Any]) -> dict[str, object]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return dict(value)


class TaskStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def claim(self, lease_seconds: int) -> TaskClaim | None:
        current = now()
        async with self.sessions.begin() as session:
            expired = list(
                (
                    await session.scalars(
                        select(Task)
                        .where(
                            Task.status == TaskStatus.running.value,
                            Task.lease_until.is_not(None),
                            Task.lease_until < current,
                        )
                        .with_for_update(skip_locked=True)
                    )
                ).all()
            )
            for task in expired:
                task.status = TaskStatus.queued.value
                task.phase = task.phase or "queued"
                task.lease_token = None
                task.lease_until = None

            selected = await session.scalar(
                select(Task)
                .where(Task.status == TaskStatus.queued.value)
                .order_by(Task.created_at, Task.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if selected is None:
                return None
            task = selected

            token = secrets.token_hex(24)
            task.status = TaskStatus.running.value
            task.phase = "running"
            task.lease_token = token
            task.lease_until = current + timedelta(seconds=lease_seconds)
            task.attempts += 1
            task.started_at = task.started_at or current
            task.completed_at = None
            return TaskClaim(task_id=task.id, lease_token=token)

    async def renew(self, claim: TaskClaim, lease_seconds: int) -> None:
        result = await self._execute_update(
            update(Task)
            .where(
                Task.id == claim.task_id,
                Task.lease_token == claim.lease_token,
                Task.status == TaskStatus.running.value,
            )
            .values(lease_until=now() + timedelta(seconds=lease_seconds))
        )
        if not result:
            raise LostTaskLease("任务执行权已失效")

    async def start_step(self, claim: TaskClaim, key: str, input_state: dict[str, object]) -> None:
        current = now()
        async with self.sessions.begin() as session:
            task = await self._owned(session, claim)
            step = await session.scalar(
                select(TaskStep)
                .where(TaskStep.task_id == task.id, TaskStep.key == key)
                .with_for_update()
            )
            if step is None:
                ordinal = await session.scalar(
                    select(func.max(TaskStep.ordinal)).where(TaskStep.task_id == task.id)
                )
                step = TaskStep(
                    task_id=task.id,
                    key=key,
                    ordinal=(ordinal + 1) if ordinal is not None else 0,
                )
                session.add(step)
                await session.flush()
            step.status = "running"
            step.attempts += 1
            step.input_state = self._strip_runtime_state(input_state)
            step.output_state = {}
            step.error_code = None
            step.error_message = None
            step.started_at = current
            step.completed_at = None
            task.phase = key

    async def save_state(
        self,
        claim: TaskClaim,
        state: dict[str, object],
        phase: str,
    ) -> None:
        current = now()
        persisted = self._strip_runtime_state(state)
        async with self.sessions.begin() as session:
            task = await self._owned(session, claim)
            task.state = persisted
            task.phase = phase
            step = await session.scalar(
                select(TaskStep)
                .where(TaskStep.task_id == task.id, TaskStep.key == phase)
                .with_for_update()
            )
            if step is None:
                ordinal = await session.scalar(
                    select(func.max(TaskStep.ordinal)).where(TaskStep.task_id == task.id)
                )
                step = TaskStep(
                    task_id=task.id,
                    key=phase,
                    ordinal=(ordinal + 1) if ordinal is not None else 0,
                )
                session.add(step)
            step.status = "succeeded"
            step.output_state = persisted
            step.completed_at = current

    async def append_event(self, task_id: str, event: BaseModel | dict[str, Any]) -> None:
        payload = json_payload(event)
        async with self.sessions.begin() as session:
            task = await session.scalar(select(Task.id).where(Task.id == task_id).with_for_update())
            if task is None:
                raise LookupError(f"Task not found: {task_id}")
            sequence = await session.scalar(
                select(func.max(TaskEvent.sequence)).where(TaskEvent.task_id == task_id)
            )
            session.add(
                TaskEvent(
                    task_id=task_id,
                    sequence=(sequence or 0) + 1,
                    event_type=str(payload["type"]),
                    payload=payload,
                )
            )

    async def events(self, task_id: str, after: int = 0) -> list[EventRecord]:
        async with self.sessions() as session:
            return [
                EventRecord(sequence=row.sequence, payload=row.payload)
                for row in (
                    (
                        await session.scalars(
                            select(TaskEvent)
                            .where(TaskEvent.task_id == task_id, TaskEvent.sequence > after)
                            .order_by(TaskEvent.sequence)
                        )
                    ).all()
                )
            ]

    async def latest_for_run(self, run_id: str) -> TaskSnapshot | None:
        async with self.sessions() as session:
            statement = select(Task).where(Task.decision_run_id == run_id)
            task = await session.scalar(statement.order_by(Task.created_at.desc(), Task.id.desc()))
            return TaskSnapshot(id=task.id, status=task.status) if task else None

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
            task.error_message = message[:500]
            task.lease_token = None
            task.lease_until = None
            task.completed_at = now()
            return True

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

    async def _execute_update(self, statement: Any) -> bool:
        async with self.sessions.begin() as session:
            result = await session.execute(statement)
            return bool(cast(CursorResult[Any], result).rowcount)

    @staticmethod
    def _strip_runtime_state(state: dict[str, object]) -> dict[str, object]:
        return {key: value for key, value in state.items() if key != "lease_token"}


TaskHandler = Callable[[TaskClaim], Awaitable[None]]


class TaskWorker:
    def __init__(
        self,
        store: TaskStore,
        handler: TaskHandler,
        lease_seconds: int = 60,
        poll_seconds: float = 1,
    ) -> None:
        self.store = store
        self.handler = handler
        self.lease_seconds = lease_seconds
        self.poll_seconds = poll_seconds
        self._stop = asyncio.Event()

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                claim = await self.store.claim(self.lease_seconds)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Task claim failed")
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.poll_seconds)
                except TimeoutError:
                    continue
                continue
            if claim is None:
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.poll_seconds)
                except TimeoutError:
                    continue
                continue
            try:
                await self.handler(claim)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Task handler exited unexpectedly: %s", claim.task_id)

    async def stop(self) -> None:
        self._stop.set()
