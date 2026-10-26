from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

from pydantic import TypeAdapter

from app.core.clock import now
from app.core.errors import AppError
from app.modules.auth.service import AuthService
from app.modules.decision.service.queries import DecisionQueryService
from app.modules.decision.workflow.events import (
    DecisionEvent,
    Heartbeat,
    ResultEvent,
    RunFailed,
    WorkflowError,
)
from app.modules.task.ports import TaskStore

EVENT_ADAPTER: TypeAdapter[DecisionEvent] = TypeAdapter(DecisionEvent)


class DecisionStreamService:
    def __init__(self, tasks: TaskStore, queries: DecisionQueryService, auth: AuthService) -> None:
        self.tasks = tasks
        self.queries = queries
        self.auth = auth

    async def stream(
        self, user_id: str, run_id: str, token: str | None
    ) -> AsyncIterator[DecisionEvent]:
        current_task_id: str | None = None
        last_sequence = 0
        last_heartbeat = float("-inf")
        while True:
            try:
                current = await self.auth.authenticate(token)
                if current.user.id != user_id:
                    return
                status = await self.queries.stream_status(user_id, run_id)
                if status.task_id != current_task_id:
                    current_task_id = status.task_id
                    last_sequence = 0
                if current_task_id:
                    for row in await self.tasks.events(current_task_id, last_sequence):
                        event = EVENT_ADAPTER.validate_python(row.payload)
                        last_sequence = row.sequence
                        if event.type == "result":
                            data = await self.queries.get_for_user(user_id, run_id)
                            yield ResultEvent(data=data.model_dump(mode="json", by_alias=True))
                        else:
                            yield event
                        if event.type in {"result", "runFailed"}:
                            return
                if status.status == "completed":
                    data = await self.queries.get_for_user(user_id, run_id)
                    yield ResultEvent(data=data.model_dump(mode="json", by_alias=True))
                    return
                if status.status == "failed":
                    yield RunFailed(error=WorkflowError(
                        code=status.error_code or "RUN_FAILED",
                        message="排队超过等待时限，请重新推荐。" if status.error_code == "QUEUE_TIMEOUT" else "推荐未完成，请检查服务或重试",
                        retryable=True,
                    ))
                    return
            except AppError as error:
                yield RunFailed(error=WorkflowError(
                    code=error.code, message=error.message, retryable=error.retryable,
                ))
                return
            if time.monotonic() - last_heartbeat >= 15:
                yield Heartbeat(timestamp=now())
                last_heartbeat = time.monotonic()
            await asyncio.sleep(1)
