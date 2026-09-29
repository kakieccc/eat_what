from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

from pydantic import TypeAdapter

from app.application.auth.service import AuthService
from app.application.decision.queries import DecisionQueryService
from app.application.task.ports import TaskStore
from app.core.clock import now
from app.workflows.food_decision.events import (
    ConfirmationRequired,
    DecisionEvent,
    Heartbeat,
    ResultEvent,
    RunFailed,
    WorkflowError,
)

EVENT_ADAPTER: TypeAdapter[DecisionEvent] = TypeAdapter(DecisionEvent)


class DecisionStreamService:
    def __init__(self, tasks: TaskStore, queries: DecisionQueryService, auth: AuthService) -> None:
        self.tasks = tasks
        self.queries = queries
        self.auth = auth

    async def stream(
        self, user_id: str, run_id: str, request_id: str, token: str | None
    ) -> AsyncIterator[DecisionEvent]:
        current_task_id: str | None = None
        last_sequence = 0
        last_heartbeat = time.monotonic()
        while True:
            current = await self.auth.authenticate(token)
            if current.user.id != user_id:
                return
            task = await self.tasks.latest_for_run(run_id)
            if task is not None and task.id != current_task_id:
                current_task_id = task.id
                last_sequence = 0
            if current_task_id:
                for row in await self.tasks.events(current_task_id, last_sequence):
                    event = EVENT_ADAPTER.validate_python(row.payload)
                    last_sequence = row.sequence
                    yield event
                    if event.type in {"result", "runFailed", "confirmationRequired"}:
                        return
            data = await self.queries.get_for_user(user_id, run_id)
            if data.status == "completed":
                yield ResultEvent(data=data.model_dump(mode="json", by_alias=True))
                return
            if data.status == "awaitingConfirmation":
                yield ConfirmationRequired(data=data.model_dump(mode="json", by_alias=True))
                return
            if data.status == "failed":
                yield RunFailed(
                    error=WorkflowError(
                        code=data.error_code or "RUN_FAILED",
                        message="推荐未完成，请检查服务或重试",
                        retryable=True,
                    )
                )
                return
            if time.monotonic() - last_heartbeat >= 15:
                yield Heartbeat(timestamp=now())
                last_heartbeat = time.monotonic()
            await asyncio.sleep(0.5)
