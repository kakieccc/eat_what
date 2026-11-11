from __future__ import annotations

import os
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
        os.environ["DATABASE_URL"],
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=True,
        # Background exception tracebacks must not include SQL bound values.
        hide_parameters=True,
    )
    return async_sessionmaker(engine, expire_on_commit=False)


def engine_of(sessions: async_sessionmaker[AsyncSession]) -> AsyncEngine:
    return cast(AsyncEngine, sessions.kw["bind"])
