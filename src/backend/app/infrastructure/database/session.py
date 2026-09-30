from __future__ import annotations

from typing import cast

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings


def create_sessions(settings: Settings) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        settings.db_url,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
    )
    return async_sessionmaker(engine, expire_on_commit=False)


def engine_of(sessions: async_sessionmaker[AsyncSession]) -> AsyncEngine:
    return cast(AsyncEngine, sessions.kw["bind"])
