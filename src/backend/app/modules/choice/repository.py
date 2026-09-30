from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.ids import lock_id
from app.modules.choice.transaction import ChoiceTransaction


class ChoiceRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    @asynccontextmanager
    async def transaction(self, user_id: str, key: str) -> AsyncIterator[ChoiceTransaction]:
        async with self.sessions.begin() as session:
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": lock_id(user_id + key + "choice")},
            )
            yield ChoiceTransaction(session, user_id)
