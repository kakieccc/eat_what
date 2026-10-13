import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime

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
from app.modules.location.schemas import Origin, Point
from app.modules.places.schemas import Place

log = logging.getLogger("food.amap")


class AmapGeoPlaceProvider:
    def __init__(self, client: AmapClient, cache: AmapCache, timeout_seconds: float) -> None:
        self.client = client
        self.cache = cache
        self.timeout_seconds = timeout_seconds

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

    async def _fetch[Response: RawResponse, Result](
        self,
        operation: str,
        params: dict[str, str],
        schema: type[Response],
        mapper: Callable[[Response, datetime], Result],
        deadline: float,
    ) -> Result:
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
        entry = await self.client.request(operation, params, deadline=deadline)
        try:
            result = mapper(schema.model_validate(entry.payload), entry.fetched_at)
        except (ValueError, TypeError):
            log.warning(
                json.dumps(
                    {
                        "event": "amapOperationFailed",
                        "operation": operation,
                        "error": "AMAP_SCHEMA_ERROR",
                    }
                )
            )
            raise AppError("AMAP_SCHEMA_ERROR", "地图响应格式异常", 502) from None
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError
        await self.cache.write(operation, params, entry, empty=not result)
        return result

    async def search(
        self,
        origin: Point,
        radius: int,
        limit: int = 30,
        keywords: str = "",
        *,
        deadline: float | None = None,
    ) -> list[Place]:
        operation = "/v3/place/around"
        async with self._budget(operation, deadline) as until:
            unique: dict[str, Place] = {}
            for page in range(1, 3):
                batch = await self._fetch(
                    operation,
                    {
                        "location": mappers.coordinates(origin),
                        "radius": str(radius),
                        "types": "050000",
                        "extensions": "all",
                        "offset": "25",
                        "page": str(page),
                        "sortrule": "distance",
                        "keywords": keywords,
                    },
                    PlaceResponse,
                    lambda response, fetched_at: mappers.places(response, origin, fetched_at),
                    until,
                )
                unique.update((place.id, place) for place in batch)
                if len(unique) >= limit or len(batch) < 25:
                    break
            return list(unique.values())[:limit]

    async def detail(
        self, external_id: str, origin: Point, *, deadline: float | None = None
    ) -> Place:
        operation = "/v3/place/detail"
        async with self._budget(operation, deadline) as until:
            rows = await self._fetch(
                operation,
                {"id": external_id, "extensions": "all"},
                PlaceResponse,
                lambda response, fetched_at: mappers.places(response, origin, fetched_at),
                until,
            )
            if not rows:
                raise AppError("PLACE_NOT_FOUND", "地点详情暂不可用", 404)
            return rows[0]

    async def reverse(self, origin: Point, *, deadline: float | None = None) -> Origin:
        operation = "/v3/geocode/regeo"
        async with self._budget(operation, deadline) as until:
            return await self._fetch(
                operation,
                {"location": mappers.coordinates(origin), "extensions": "base"},
                ReverseResponse,
                lambda response, _: mappers.reverse(response, origin),
                until,
            )

    async def tips(self, keywords: str, *, deadline: float | None = None) -> list[Origin]:
        operation = "/v3/assistant/inputtips"
        async with self._budget(operation, deadline) as until:
            return await self._fetch(
                operation,
                {"keywords": keywords, "datatype": "poi"},
                TipsResponse,
                lambda response, _: mappers.tips(response),
                until,
            )

    @staticmethod
    def navigation(place: Place) -> str:
        return mappers.navigation(place)
