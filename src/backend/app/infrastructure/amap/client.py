import asyncio
import json
import logging
import os
import random
from typing import cast

import httpx
from pydantic import JsonValue

from app.core.clock import now
from app.core.concurrency import deadline_after
from app.core.config import Settings
from app.core.errors import AppError
from app.infrastructure.amap.schemas import FetchedResponse

log = logging.getLogger("food.amap")

OPERATIONS = {
    "/v3/place/around",
    "/v3/geocode/regeo",
    "/v3/assistant/inputtips",
}
RETRYABLE_INFOCODES = {
    "10014",
    "10015",
    "10016",
    "10017",
    "10019",
    "10020",
    "10021",
    "10029",
}
RETRYABLE_HTTP_STATUSES = {429, 500, 502, 503, 504}


def unavailable(retryable: bool = True) -> AppError:
    return AppError("AMAP_UNAVAILABLE", "地图服务暂时不可用", 502, retryable)

class AmapClient:
    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self.client = client
        self.key = os.environ["AMAP_WEB_SERVICE_KEY"]
        self.operation_timeout_seconds = settings.amap_operation_timeout_seconds
        self.timeout = httpx.Timeout(
            connect=settings.amap_connect_timeout_seconds,
            pool=settings.amap_pool_timeout_seconds,
            read=settings.amap_timeout_seconds,
            write=settings.amap_timeout_seconds,
        )
        self.semaphore = asyncio.Semaphore(settings.amap_request_concurrency)
        self.interval_seconds = settings.amap_request_interval_seconds
        self.locks = {operation: asyncio.Lock() for operation in OPERATIONS}
        self.next_request_at = dict.fromkeys(OPERATIONS, 0.0)

    async def _wait_for_slot(self, operation: str) -> None:
        # Hold the lock through the delay so waiters cannot reserve the same request time.
        async with self.locks[operation]:
            loop = asyncio.get_running_loop()
            await asyncio.sleep(max(0.0, self.next_request_at[operation] - loop.time()))
            self.next_request_at[operation] = loop.time() + self.interval_seconds

    async def request(
        self, operation: str, params: dict[str, str], *, deadline: float | None = None
    ) -> FetchedResponse:
        if operation not in OPERATIONS:
            raise AppError("AMAP_INVALID_OPERATION", "地图操作不受支持")
        until = deadline_after(self.operation_timeout_seconds, deadline)
        loop = asyncio.get_running_loop()
        started = loop.time()
        attempt = 0
        try:
            async with asyncio.timeout_at(until):
                for attempt in range(1, 4):
                    started = loop.time()
                    retryable = True
                    try:
                        async with self.semaphore:
                            await self._wait_for_slot(operation)
                            response = await self.client.get(
                                "https://restapi.amap.com" + operation,
                                params={**params, "key": self.key},
                                timeout=self.timeout,
                            )
                    except httpx.TransportError as error:
                        self._log(operation, started, attempt, type(error).__name__)
                    else:
                        code: str | None = None
                        if not 200 <= response.status_code < 300:
                            retryable = response.status_code in RETRYABLE_HTTP_STATUSES
                            self._log(
                                operation,
                                started,
                                attempt,
                                "http_status",
                                http_status=response.status_code,
                            )
                        else:
                            try:
                                payload: object = response.json()
                            except ValueError:
                                payload = None
                            if (
                                not isinstance(payload, dict)
                                or not isinstance(payload.get("status"), str)
                                or not isinstance(payload.get("infocode", ""), str)
                            ):
                                self._log(operation, started, attempt, "AMAP_SCHEMA_ERROR")
                                raise AppError(
                                    "AMAP_SCHEMA_ERROR", "地图响应格式异常", 502
                                ) from None
                            if payload["status"] == "1":
                                result = FetchedResponse(
                                    payload=cast(dict[str, JsonValue], payload), fetched_at=now()
                                )
                                self._log(operation, started, attempt)
                                return result
                            code = payload.get("infocode", "")
                            retryable = code in RETRYABLE_INFOCODES or code == "10004"
                            self._log(operation, started, attempt, "upstream_error", infocode=code)
                        # The minute limit cannot be resolved by short in-call retries.
                        if not retryable or code == "10004":
                            raise unavailable(retryable) from None
                    delay = 0.2 * 2 ** (attempt - 1) + random.uniform(0, 0.1)
                    if attempt == 3 or delay >= until - loop.time():
                        raise unavailable(retryable) from None
                    await asyncio.sleep(delay)
        except TimeoutError:
            self._log(operation, started, attempt, "deadline")
            raise unavailable() from None
        except asyncio.CancelledError:
            error_kind = "deadline" if loop.time() >= until else "cancelled"
            self._log(operation, started, attempt, error_kind)
            raise
        raise AssertionError("unreachable")

    @staticmethod
    def _log(
        operation: str,
        started: float,
        attempt: int,
        error: str | None = None,
        *,
        infocode: str | None = None,
        http_status: int | None = None,
    ) -> None:
        log.info(
            json.dumps(
                {
                    "event": "amapRequest",
                    "operation": operation,
                    "attempt": attempt,
                    "durationMs": int((asyncio.get_running_loop().time() - started) * 1000),
                    "cacheHit": False,
                    "error": error,
                    "infocode": infocode,
                    "httpStatus": http_status,
                }
            )
        )
