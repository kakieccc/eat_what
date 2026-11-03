from typing import Protocol

from app.modules.history.schemas import HistoryCursor, HistoryPage


class HistoryRepository(Protocol):
    async def list_sessions(self, user_id: str, cursor: HistoryCursor | None, limit: int) -> HistoryPage: ...
    async def runs(self, user_id: str, session_id: str) -> list[str]: ...
