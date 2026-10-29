import asyncio
import logging
from collections.abc import Callable
from typing import Any

from pwdlib import PasswordHash

from app.core.errors import AppError

log = logging.getLogger("food.auth")


class Argon2PasswordHasher:
    def __init__(self, concurrency: int = 1, max_waiters: int = 2, wait_seconds: float = 1) -> None:
        self._passwords = PasswordHash.recommended()
        self.dummy_hash = self._passwords.hash("not-a-real-account-password")
        self._slots = asyncio.Semaphore(concurrency)
        self._max_waiters = max_waiters
        self._wait_seconds = wait_seconds
        self._waiters = 0
        self._running: set[asyncio.Task[Any]] = set()
        self._closing = False

    @staticmethod
    def _busy() -> AppError:
        return AppError("AUTH_BUSY", "认证服务繁忙，请稍后再试", 503, True, retry_after=1)

    def _finished(self, task: asyncio.Task[Any]) -> None:
        self._running.discard(task)
        self._slots.release()
        if not task.cancelled() and (error := task.exception()) is not None:
            log.error("Password computation failed: %s", type(error).__name__)

    async def _compute[T](self, operation: Callable[[], T]) -> T:
        if self._closing or (self._slots.locked() and self._waiters >= self._max_waiters):
            raise self._busy()
        self._waiters += 1
        try:
            async with asyncio.timeout(self._wait_seconds):
                await self._slots.acquire()
        except TimeoutError:
            raise self._busy() from None
        finally:
            self._waiters -= 1
        if self._closing:
            self._slots.release()
            raise self._busy()
        task = asyncio.create_task(asyncio.to_thread(operation))
        self._running.add(task)
        # Cancelling an HTTP request cannot stop an already running password thread.
        task.add_done_callback(self._finished)
        return await asyncio.shield(task)

    async def hash(self, password: str) -> str:
        return await self._compute(lambda: self._passwords.hash(password))

    async def verify(self, password: str, encoded: str) -> bool:
        return await self._compute(lambda: self._passwords.verify(password, encoded))

    async def aclose(self) -> None:
        self._closing = True
        await asyncio.gather(*(asyncio.shield(task) for task in self._running), return_exceptions=True)
