import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from app.core.concurrency import deadline_after
from app.core.errors import AppError
from app.infrastructure.amap import mappers
from app.infrastructure.amap.cache import AmapCache
from app.infrastructure.amap.client import AmapClient, unavailable
from app.infrastructure.amap.schemas import (
    PlaceResponse,
    RawResponse,
    ReverseResponse,
    TipsResponse,
)
from app.modules.location.geometry import distance
from app.modules.location.schemas import Origin, Point
from app.modules.places.schemas import Place, PlaceSearchPage

log = logging.getLogger("food.amap")


@dataclass
class InFlight:
    task: asyncio.Task[object]
    waiters: int = 0


class AmapGeoPlaceProvider:
    def __init__(self, client: AmapClient, cache: AmapCache, timeout_seconds: float) -> None:
        self.client = client
        self.cache = cache
        self.timeout_seconds = timeout_seconds
        self._inflight: dict[str, InFlight] = {}

    @asynccontextmanager
    async def _budget(self, operation: str, deadline: float | None) -> AsyncIterator[float]:
        started = asyncio.get_running_loop().time()
        until = deadline_after(self.timeout_seconds, deadline)
        try:
            async with asyncio.timeout_at(until):
                yield until
                if asyncio.get_running_loop().time() >= until:
                    raise TimeoutError
        except TimeoutError:
            log.warning(
                json.dumps(
                    {
                        "event": "amapOperationFailed",
                        "operation": operation,
                        "error": "deadline",
                        "durationMs": int((asyncio.get_running_loop().time() - started) * 1000),
                    }
                )
            )
            raise unavailable() from None

    async def _cached[Response: RawResponse, Result](
        self,
        operation: str,
        params: dict[str, str],
        schema: type[Response],
        mapper: Callable[[Response, datetime], Result],
    ) -> Result | None:
        started = asyncio.get_running_loop().time()
        cached = await self.cache.read(operation, params)
        if cached is not None:
            try:
                result = mapper(schema.model_validate(cached.payload), cached.fetched_at)
            except (ValueError, TypeError):
                log.warning(
                    json.dumps(
                        {
                            "event": "amapCacheInvalid",
                            "operation": operation,
                            "error": "invalid_response",
                        }
                    )
                )
            else:
                log.info(
                    json.dumps(
                        {
                            "event": "amapCache",
                            "operation": operation,
                            "cacheHit": True,
                            "durationMs": int((asyncio.get_running_loop().time() - started) * 1000),
                        }
                    )
                )
                return result
        return None

    async def _load[Response: RawResponse, Result](
        self, operation: str, params: dict[str, str], schema: type[Response],
        mapper: Callable[[Response, datetime], Result],
    ) -> Result:
        # The shared operation has its own budget; each waiter keeps its caller's deadline.
        async with self._budget(operation, None) as until:
            cached = await self._cached(operation, params, schema, mapper)
            if cached is not None:
                return cached
            entry = await self.client.request(operation, params, deadline=until)
            try:
                result = mapper(schema.model_validate(entry.payload), entry.fetched_at)
            except (ValueError, TypeError):
                log.warning(json.dumps({
                    "event": "amapOperationFailed", "operation": operation, "error": "AMAP_SCHEMA_ERROR",
                }))
                raise AppError("AMAP_SCHEMA_ERROR", "地图响应格式异常", 502) from None
            if asyncio.get_running_loop().time() >= until:
                raise TimeoutError
            empty = not result.places if isinstance(result, PlaceSearchPage) else not result
            await self.cache.write(operation, params, entry, empty=empty)
            return result

    async def _fetch[Response: RawResponse, Result](
        self, operation: str, params: dict[str, str], schema: type[Response],
        mapper: Callable[[Response, datetime], Result],
    ) -> Result:
        cached = await self._cached(operation, params, schema, mapper)
        if cached is not None:
            return cached
        key = self.cache.key(operation, params)
        flight = self._inflight.get(key)
        if flight is None:
            flight = InFlight(asyncio.create_task(self._load(operation, params, schema, mapper)))
            self._inflight[key] = flight

            def finished(task: asyncio.Task[object]) -> None:
                if self._inflight.get(key) is flight:
                    del self._inflight[key]
                if not task.cancelled():
                    task.exception()

            flight.task.add_done_callback(finished)
        flight.waiters += 1
        try:
            # One cancelled waiter must not cancel the shared request for all other callers.
            return cast(Result, await asyncio.shield(flight.task))
        finally:
            flight.waiters -= 1
            if flight.waiters == 0 and not flight.task.done():
                if self._inflight.get(key) is flight:
                    del self._inflight[key]
                flight.task.cancel()
                await asyncio.gather(flight.task, return_exceptions=True)

    async def search(
        self,
        origin: Point,
        radius: int,
        limit: int = 25,
        keywords: str = "",
        *,
        deadline: float | None = None,
        page: int = 1,
    ) -> PlaceSearchPage:
        operation = "/v3/place/around"
        async with self._budget(operation, deadline):
            result = await self._fetch(
                operation,
                {
                    "location": mappers.coordinates(origin),
                    "radius": str(radius),
                    "types": "050000",
                    "extensions": "all",
                    "offset": str(min(limit, 25)),
                    "page": str(page),
                    "sortrule": "distance",
                    "keywords": keywords,
                },
                PlaceResponse,
                lambda response, fetched_at: PlaceSearchPage(
                    places=mappers.places(response, origin, fetched_at),
                    has_more=len(response.pois) == min(limit, 25),
                ),
            )
            return result.model_copy(update={"places": [
                place.model_copy(update={
                    "straight_line_distance_meters": distance(origin, place.location),
                }) for place in result.places
            ]})

    async def reverse(self, origin: Point, *, deadline: float | None = None) -> Origin:
        operation = "/v3/geocode/regeo"
        async with self._budget(operation, deadline):
            result = await self._fetch(
                operation,
                {"location": mappers.coordinates(origin), "extensions": "base"},
                ReverseResponse,
                lambda response, _: mappers.reverse(response, origin),
            )
            return result.model_copy(update={
                "latitude": origin.latitude, "longitude": origin.longitude,
            })

    async def tips(self, keywords: str, *, deadline: float | None = None) -> list[Origin]:
        operation = "/v3/assistant/inputtips"
        async with self._budget(operation, deadline):
            return await self._fetch(
                operation,
                {"keywords": keywords, "datatype": "poi"},
                TipsResponse,
                lambda response, _: mappers.tips(response),
            )

    @staticmethod
    def navigation(place: Place) -> str:
        return mappers.navigation(place)
