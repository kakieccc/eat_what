from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from pydantic import TypeAdapter

from app.core.clock import now
from app.core.errors import AppError
from app.modules.auth.service import AuthService
from app.modules.decision.service.queries import DecisionQueryService
from app.modules.decision.workflow.events import (
    DecisionEvent,
    Heartbeat,
    ProgressEvent,
    ResultEvent,
    RunFailed,
    WorkflowError,
)
from app.modules.task.ports import TaskStore

EVENT_ADAPTER: TypeAdapter[ProgressEvent] = TypeAdapter(ProgressEvent)


class DecisionStreamService:
    def __init__(
        self, tasks: TaskStore, queries: DecisionQueryService, auth: AuthService,
        max_per_user: int = 2, max_connections: int = 8,
    ) -> None:
        self.tasks = tasks
        self.queries = queries
        self.auth = auth
        self.max_per_user = max_per_user
        self.max_connections = max_connections
        self._connections: dict[str, int] = {}
        self._connection_count = 0

    @asynccontextmanager
    async def connection(self, user_id: str) -> AsyncIterator[None]:
        # No await between checking and reserving: counters are atomic within this API process.
        count = self._connections.get(user_id, 0)
        if count >= self.max_per_user:
            raise AppError("USER_STREAM_LIMIT_REACHED", "当前账号的实时进度连接已满", 429, True, retry_after=2)
        if self._connection_count >= self.max_connections:
            raise AppError("STREAM_CAPACITY_REACHED", "实时进度连接已满", 503, True, retry_after=2)
        self._connections[user_id] = count + 1
        self._connection_count += 1
        try:
            yield
        finally:
            remaining = self._connections[user_id] - 1
            if remaining:
                self._connections[user_id] = remaining
            else:
                del self._connections[user_id]
            self._connection_count -= 1

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
                        yield event
                        if event.type == "runFailed":
                            return
                if status.status == "completed":
                    # Build terminal results from committed business rows, not stored progress events.
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
