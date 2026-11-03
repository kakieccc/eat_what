from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Any, cast

from pydantic import BaseModel
from sqlalchemy import delete, func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import now
from app.modules.decision.models import DecisionRun
from app.modules.decision.workflow.events import RunFailed, WorkflowError
from app.modules.task.errors import LostTaskLease
from app.modules.task.models import Task, TaskEvent, TaskStatus, TaskStep
from app.modules.task.types import EventRecord, TaskClaim


async def record_event(
    session: AsyncSession, task_id: str, event: BaseModel
) -> None:
    # Callers hold the task row lock to serialize event sequences.
    payload = event.model_dump(mode="json")
    sequence = await session.scalar(
        select(func.max(TaskEvent.sequence)).where(TaskEvent.task_id == task_id)
    )
    session.add(TaskEvent(
        task_id=task_id, sequence=(sequence or 0) + 1,
        event_type=str(payload["type"]), payload=payload,
    ))


class TaskStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], queue_timeout_seconds: float = 60) -> None:
        self.sessions = sessions
        self.queue_timeout_seconds = queue_timeout_seconds

    async def expire_queued(self) -> None:
        current = now()
        async with self.sessions.begin() as session:
            tasks = (await session.scalars(select(Task).where(
                Task.status == TaskStatus.queued.value, Task.started_at.is_(None),
                Task.created_at <= current - timedelta(seconds=self.queue_timeout_seconds),
            ).with_for_update(skip_locked=True))).all()
            for task in tasks:
                task.status = TaskStatus.failed.value
                task.phase = "failed"
                task.error_code = "QUEUE_TIMEOUT"
                task.error_message = "排队超过等待时限，请重新推荐。"
                task.completed_at = current
                run = await session.get(DecisionRun, task.decision_run_id, with_for_update=True)
                if run is not None and run.status == "pending":
                    run.status = "failed"
                    run.error_code = task.error_code
                    run.completed_at = current
                await record_event(session, task.id, RunFailed(error=WorkflowError(
                    code=task.error_code, message=task.error_message, retryable=True,
                )))

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
                task.phase = "queued"
                task.lease_token = None
                task.lease_until = None
                # Reclaimed tasks restart from input; keep event sequences for connected clients.
                await session.execute(delete(TaskStep).where(TaskStep.task_id == task.id))

            selected = await session.scalar(
                select(Task)
                .where(
                    Task.status == TaskStatus.queued.value,
                    (Task.started_at.is_not(None)) | (Task.created_at > current - timedelta(seconds=self.queue_timeout_seconds)),
                )
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
            # Each claim gets a fresh execution budget, excluding time waiting in the queue.
            task.started_at = current
            task.completed_at = None
            return TaskClaim(task_id=task.id, lease_token=token)

    async def renew(self, claim: TaskClaim, lease_seconds: int) -> None:
        async with self.sessions.begin() as session:
            result = await session.execute(
                update(Task)
                .where(
                    Task.id == claim.task_id,
                    Task.lease_token == claim.lease_token,
                    Task.status == TaskStatus.running.value,
                    Task.lease_until > now(),
                )
                .values(lease_until=now() + timedelta(seconds=lease_seconds))
            )
            if not cast(CursorResult[Any], result).rowcount:
                raise LostTaskLease("任务执行权已失效")

    async def start_step(self, claim: TaskClaim, key: str) -> None:
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
            step.error_code = None
            step.error_message = None
            step.started_at = current
            step.completed_at = None
            task.phase = key

    async def complete_step(self, claim: TaskClaim, key: str) -> None:
        async with self.sessions.begin() as session:
            task = await self._owned(session, claim)
            step = await session.scalar(
                select(TaskStep)
                .where(TaskStep.task_id == task.id, TaskStep.key == key)
                .with_for_update()
            )
            assert step is not None
            step.status = "succeeded"
            step.completed_at = now()

    async def append_event(self, claim: TaskClaim, event: BaseModel) -> None:
        async with self.sessions.begin() as session:
            task = await self._owned(session, claim)
            await record_event(session, task.id, event)

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

    async def _owned(self, session: AsyncSession, claim: TaskClaim) -> Task:
        task = await session.scalar(
            select(Task)
            .where(
                Task.id == claim.task_id,
                Task.lease_token == claim.lease_token,
                Task.status == TaskStatus.running.value,
                Task.lease_until > now(),
            )
            .with_for_update()
        )
        if task is None:
            raise LostTaskLease("任务执行权已失效")
        return task
