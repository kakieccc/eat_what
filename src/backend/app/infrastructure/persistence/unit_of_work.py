from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class UnitOfWork:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]):
        self.sessions = sessions

    @asynccontextmanager
    async def read(self) -> AsyncIterator[AsyncSession]:
        async with self.sessions() as session:
            yield session

    @asynccontextmanager
    async def write(self) -> AsyncIterator[AsyncSession]:
        async with self.sessions.begin() as session:
            yield session
