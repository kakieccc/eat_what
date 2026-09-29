from app.application.history.ports import HistoryRepository
from app.domain.history.models import HistoryPage


class HistoryService:
    def __init__(self, repository: HistoryRepository) -> None:
        self.repository = repository

    async def list_sessions(self, user_id: str, cursor: str | None, limit: int) -> HistoryPage:
        return await self.repository.list_sessions(user_id, cursor, limit)

    async def runs(self, user_id: str, session_id: str) -> list[str]:
        return await self.repository.runs(user_id, session_id)

    async def ready(self) -> None:
        await self.repository.ready()
