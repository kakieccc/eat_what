import hashlib
import json
import logging
from datetime import timedelta

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import now
from app.infrastructure.amap.models import PlaceCache
from app.infrastructure.amap.schemas import FetchedResponse

log = logging.getLogger("food.amap")


class AmapCache:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        ttl_seconds: int,
        empty_ttl_seconds: int,
    ) -> None:
        self.sessions = sessions
        self.ttl_seconds = ttl_seconds
        self.empty_ttl_seconds = empty_ttl_seconds

    @staticmethod
    def key(operation: str, params: dict[str, str]) -> str:
        return hashlib.sha256(
            json.dumps([operation, params], sort_keys=True).encode()
        ).hexdigest()

    async def read(self, operation: str, params: dict[str, str]) -> FetchedResponse | None:
        async with self.sessions() as session:
            cached = (
                await session.execute(
                    select(PlaceCache.payload).where(
                        PlaceCache.cache_key == self.key(operation, params),
                        PlaceCache.expires_at > now(),
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
        ttl = self.empty_ttl_seconds if empty else self.ttl_seconds
        payload = entry.model_dump(mode="json")
        expires_at = entry.fetched_at + timedelta(seconds=ttl)
        async with self.sessions.begin() as session:
            await session.execute(
                insert(PlaceCache)
                .values(
                    cache_key=self.key(operation, params), payload=payload, expires_at=expires_at
                )
                .on_conflict_do_update(
                    index_elements=["cache_key"],
                    set_={"payload": payload, "expires_at": expires_at, "updated_at": now()},
                )
            )
