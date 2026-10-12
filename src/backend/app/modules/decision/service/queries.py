from app.modules.decision.ports import DecisionRepository
from app.modules.decision.schemas import DecisionRunResponse
from app.modules.places.service import PlaceService


class DecisionQueryService:
    def __init__(self, repository: DecisionRepository, places: PlaceService) -> None:
        self.repository = repository
        self.places = places

    def _with_navigation(self, run: DecisionRunResponse) -> DecisionRunResponse:
        return run.model_copy(
            update={"places": [self.places.with_navigation(place) for place in run.places]}
        )

    async def get(self, run_id: str) -> DecisionRunResponse:
        return self._with_navigation(await self.repository.read(run_id))

    async def get_for_user(self, user_id: str, run_id: str) -> DecisionRunResponse:
        return self._with_navigation(await self.repository.read_for_user(user_id, run_id))

    async def response_json(self, run_id: str) -> dict[str, object]:
        return (await self.get(run_id)).model_dump(mode="json", by_alias=True)
