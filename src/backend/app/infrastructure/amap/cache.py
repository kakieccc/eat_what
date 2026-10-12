import hashlib
import json
import logging
from datetime import timedelta

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import now
from app.infrastructure.amap.models import PlaceCache, RouteCache
from app.infrastructure.amap.schemas import FetchedResponse

log = logging.getLogger("food.amap")


class AmapCache:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        place_ttl_seconds: int,
        route_ttl_seconds: int,
        empty_ttl_seconds: int,
    ) -> None:
        self.sessions = sessions
        self.place_ttl_seconds = place_ttl_seconds
        self.route_ttl_seconds = route_ttl_seconds
        self.empty_ttl_seconds = empty_ttl_seconds

    @staticmethod
    def key(operation: str, params: dict[str, str]) -> str:
        return hashlib.sha256(
            json.dumps([operation, params, "v3"], sort_keys=True).encode()
        ).hexdigest()

    async def read(self, operation: str, params: dict[str, str]) -> FetchedResponse | None:
        table = RouteCache if operation == "/v3/direction/walking" else PlaceCache
        async with self.sessions() as session:
            cached = (
                await session.execute(
                    select(table.payload).where(
                        table.cache_key == self.key(operation, params), table.expires_at > now()
                    )
                )
            ).one_or_none()
        if cached is None:
            return None
        try:
            return FetchedResponse.model_validate(cached[0])
        except ValidationError:
            log.warning(
                json.dumps(
                    {
                        "event": "amapCacheInvalid",
                        "operation": operation,
                        "error": "invalid_envelope",
                    }
                )
            )
            return None

    async def write(
        self,
        operation: str,
        params: dict[str, str],
        entry: FetchedResponse,
        *,
        empty: bool,
    ) -> None:
        table = RouteCache if operation == "/v3/direction/walking" else PlaceCache
        ttl = (
            self.empty_ttl_seconds
            if empty
            else self.route_ttl_seconds
            if table is RouteCache
            else self.place_ttl_seconds
        )
        payload = entry.model_dump(mode="json")
        expires_at = entry.fetched_at + timedelta(seconds=ttl)
        async with self.sessions.begin() as session:
            await session.execute(
                insert(table)
                .values(
                    cache_key=self.key(operation, params), payload=payload, expires_at=expires_at
                )
                .on_conflict_do_update(
                    index_elements=["cache_key"],
                    set_={"payload": payload, "expires_at": expires_at, "updated_at": now()},
                )
            )
