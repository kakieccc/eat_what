from app.modules.decision.schemas import DecisionRunResponse
from app.modules.decision.service.queries import DecisionQueryService
from app.modules.history.ports import HistoryRepository
from app.modules.history.schemas import HistoryCursor, HistoryPage
from app.modules.places.service import PlaceService


class HistoryService:
    def __init__(
        self, repository: HistoryRepository, queries: DecisionQueryService, places: PlaceService
    ) -> None:
        self.repository = repository
        self.queries = queries
        self.places = places

    async def list_sessions(self, user_id: str, cursor: HistoryCursor | None, limit: int) -> HistoryPage:
        page = await self.repository.list_sessions(user_id, cursor, limit)
        return page.model_copy(
            update={
                "items": [
                    item.model_copy(
                        update={
                            "choice": item.choice.model_copy(
                                update={"place": self.places.with_navigation(item.choice.place)}
                            )
                        }
                    )
                    for item in page.items
                ]
            }
        )

    async def runs(self, user_id: str, session_id: str) -> list[DecisionRunResponse]:
        run_ids = await self.repository.runs(user_id, session_id)
        return [await self.queries.get_for_user(user_id, run_id) for run_id in run_ids]
