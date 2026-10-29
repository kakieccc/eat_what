from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from app.modules.task.errors import LostTaskLease
from app.modules.task.ports import TaskHandler, TaskQueue
from app.modules.task.types import TaskClaim

log = logging.getLogger("food.task")


class TaskWorker:
    def __init__(
        self,
        store: TaskQueue,
        handler: TaskHandler,
        lease_seconds: int = 60,
        poll_seconds: float = 1,
        maintenance: Callable[[], Awaitable[None]] | None = None,
        concurrency: int = 2,
    ) -> None:
        self.store = store
        self.handler = handler
        self.lease_seconds = lease_seconds
        self.poll_seconds = poll_seconds
        self.maintenance = maintenance
        self.concurrency = concurrency

    async def run(self) -> None:
        async with asyncio.TaskGroup() as group:
            if self.maintenance:
                group.create_task(self._maintain())
            for _ in range(self.concurrency):
                group.create_task(self._consume())

    async def _maintain(self) -> None:
        assert self.maintenance is not None
        while True:
            try:
                await self.maintenance()
            except Exception:
                log.exception("Task queue maintenance failed")
            await asyncio.sleep(min(1, self.poll_seconds))

    async def _consume(self) -> None:
        while True:
            try:
                claim = await self.store.claim(self.lease_seconds)
            except Exception:
                log.exception("Task claim failed")
                claim = None
            if claim is None:
                await asyncio.sleep(self.poll_seconds)
                continue
            try:
                await self.execute(claim)
            except LostTaskLease:
                log.info("Task lease lost: %s", claim.task_id)
            except Exception:
                log.exception("Task handler exited unexpectedly: %s", claim.task_id)

    async def execute(self, claim: TaskClaim) -> bool:
        work = asyncio.create_task(self.handler.execute_claim(claim))
        heartbeat = asyncio.create_task(self._heartbeat(claim))
        try:
            try:
                done, _ = await asyncio.wait({work, heartbeat}, return_when=asyncio.FIRST_COMPLETED)
                if heartbeat in done:
                    await heartbeat
                await work
            finally:
                work.cancel()
                heartbeat.cancel()
                await asyncio.gather(work, heartbeat, return_exceptions=True)
        except LostTaskLease:
            raise
        except Exception as error:
            await self.handler.fail(claim, error)
            return False
        return True

    async def _heartbeat(self, claim: TaskClaim) -> None:
        while True:
            await asyncio.sleep(max(1, min(10, self.lease_seconds / 3)))
            await self.store.renew(claim, self.lease_seconds)
