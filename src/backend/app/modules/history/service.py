from app.modules.decision.schemas import DecisionRunResponse
from app.modules.decision.service.queries import DecisionQueryService
from app.modules.history.ports import HistoryRepository
from app.modules.history.schemas import HistoryPage


class HistoryService:
    def __init__(self, repository: HistoryRepository, queries: DecisionQueryService) -> None:
        self.repository = repository
        self.queries = queries

    async def list_sessions(self, user_id: str, cursor: str | None, limit: int) -> HistoryPage:
        return await self.repository.list_sessions(user_id, cursor, limit)

    async def runs(self, user_id: str, session_id: str) -> list[DecisionRunResponse]:
        run_ids = await self.repository.runs(user_id, session_id)
        return [await self.queries.get_for_user(user_id, run_id) for run_id in run_ids]
