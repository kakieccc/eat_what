import asyncio
import json
import logging
import math
import random
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import UTC
from email.utils import parsedate_to_datetime
from typing import cast

import httpx
from pydantic import JsonValue

from app.core.clock import now
from app.core.concurrency import deadline_after
from app.core.config import Settings
from app.core.errors import AppError
from app.infrastructure.amap.schemas import FetchedResponse

log = logging.getLogger("food.amap")

WALKING = "/v3/direction/walking"
OPERATIONS = {
    "/v3/place/around",
    "/v3/place/detail",
    "/v3/geocode/regeo",
    "/v3/assistant/inputtips",
    WALKING,
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


@dataclass
class RequestFailure(Exception):
    category: str
    retryable: bool = False
    retry_in_call: bool = False
    infocode: str | None = None
    http_status: int | None = None
    retry_after: float = 0


def unavailable(operation: str, retryable: bool = True) -> AppError:
    route = operation == WALKING
    return AppError(
        "ROUTE_UNAVAILABLE" if route else "AMAP_UNAVAILABLE",
        "步行路线服务不可用" if route else "地图服务暂时不可用",
        502,
        retryable,
    )


def retry_after(value: str | None) -> float:
    if not value:
        return 0
    try:
        seconds = float(value)
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                date = date.replace(tzinfo=UTC)
            seconds = (date - now()).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return 0
    return max(0, seconds) if math.isfinite(seconds) else 0


def upstream_failure(code: str) -> RequestFailure:
    if code in RETRYABLE_INFOCODES:
        return RequestFailure("upstream_transient", True, True, infocode=code)
    if code == "10004":
        # This limit resets by the minute; short in-call retries cannot resolve it.
        return RequestFailure("minute_rate_limit", True, False, infocode=code)
    if code in {"10003", "10044", "10045"}:
        category = "daily_quota"
    elif code.startswith("200"):
        category = "invalid_request"
    elif code in {
        "10001",
        "10002",
        "10005",
        "10006",
        "10007",
        "10008",
        "10009",
        "10010",
        "10012",
        "10013",
        "10026",
        "10041",
    }:
        category = "authorization"
    else:
        category = "unknown_infocode"
    return RequestFailure(category, infocode=code)


class AmapClient:
    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self.client = client
        self.key = settings.amap_web_service_key.get_secret_value()
        self.operation_timeout_seconds = settings.amap_operation_timeout_seconds
        self.timeout = httpx.Timeout(
            connect=settings.amap_connect_timeout_seconds,
            pool=settings.amap_pool_timeout_seconds,
            read=settings.amap_timeout_seconds,
            write=settings.amap_timeout_seconds,
        )
        self.semaphore = asyncio.Semaphore(settings.amap_request_concurrency)
        self.route_semaphore = asyncio.Semaphore(settings.amap_route_concurrency)
        self.interval_seconds = settings.amap_request_interval_seconds
        self.locks = {operation: asyncio.Lock() for operation in OPERATIONS}
        self.next_request_at = dict.fromkeys(OPERATIONS, 0.0)

    async def _wait_for_slot(self, operation: str) -> None:
        async with self.locks[operation]:
            loop = asyncio.get_running_loop()
            await asyncio.sleep(max(0.0, self.next_request_at[operation] - loop.time()))
            self.next_request_at[operation] = loop.time() + self.interval_seconds

    async def _attempt(self, operation: str, params: dict[str, str]) -> FetchedResponse:
        async with AsyncExitStack() as stack:
            if operation == WALKING:
                await stack.enter_async_context(self.route_semaphore)
            await stack.enter_async_context(self.semaphore)
            await self._wait_for_slot(operation)
            response = await self.client.get(
                "https://restapi.amap.com" + operation,
                params={**params, "key": self.key},
                timeout=self.timeout,
            )
        if not 200 <= response.status_code < 300:
            transient = response.status_code in RETRYABLE_HTTP_STATUSES
            raise RequestFailure(
                "http_status",
                transient,
                transient,
                http_status=response.status_code,
                retry_after=retry_after(response.headers.get("Retry-After")),
            )
        try:
            payload: object = response.json()
        except ValueError:
            raise AppError("AMAP_SCHEMA_ERROR", "地图响应格式异常", 502) from None
        if not isinstance(payload, dict) or not isinstance(payload.get("status"), str):
            raise AppError("AMAP_SCHEMA_ERROR", "地图响应格式异常", 502)
        code = payload.get("infocode", "")
        if not isinstance(code, str):
            raise AppError("AMAP_SCHEMA_ERROR", "地图响应格式异常", 502)
        if payload["status"] != "1":
            failure = upstream_failure(code)
            failure.retry_after = retry_after(response.headers.get("Retry-After"))
            raise failure
        return FetchedResponse(payload=cast(dict[str, JsonValue], payload), fetched_at=now())

    async def request(
        self, operation: str, params: dict[str, str], *, deadline: float | None = None
    ) -> FetchedResponse:
        if operation not in OPERATIONS:
            raise AppError("AMAP_INVALID_OPERATION", "地图操作不受支持")
        until = deadline_after(self.operation_timeout_seconds, deadline)
        started = asyncio.get_running_loop().time()
        attempt = 0
        try:
            async with asyncio.timeout_at(until):
                for attempt in range(1, 4):
                    started = asyncio.get_running_loop().time()
                    failure: RequestFailure
                    try:
                        result = await self._attempt(operation, params)
                    except httpx.TransportError as error:
                        failure = RequestFailure(type(error).__name__, True, True)
                    except RequestFailure as error:
                        failure = error
                    except AppError as error:
                        self._log(operation, started, attempt, error.code)
                        raise
                    else:
                        self._log(operation, started, attempt)
                        return result
                    self._log(
                        operation,
                        started,
                        attempt,
                        failure.category,
                        infocode=failure.infocode,
                        http_status=failure.http_status,
                    )
                    delay = max(
                        failure.retry_after, 0.2 * 2 ** (attempt - 1) + random.uniform(0, 0.1)
                    )
                    remaining = until - asyncio.get_running_loop().time()
                    if attempt == 3 or not failure.retry_in_call or delay >= remaining:
                        raise unavailable(operation, failure.retryable) from None
                    await asyncio.sleep(delay)
        except TimeoutError:
            self._log(operation, started, attempt, "deadline")
            raise unavailable(operation) from None
        except asyncio.CancelledError:
            error_kind = "deadline" if asyncio.get_running_loop().time() >= until else "cancelled"
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
