from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from app.modules.task.ports import TaskStore
from app.modules.task.types import TaskClaim

log = logging.getLogger("food.task")

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
