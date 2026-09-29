from app.application.decision.models import DecisionRunResponse
from app.application.decision.ports import DecisionRepository


class DecisionQueryService:
    def __init__(self, repository: DecisionRepository) -> None:
        self.repository = repository

    async def get(self, run_id: str) -> DecisionRunResponse:
        return await self.repository.read(run_id)

    async def get_for_user(self, user_id: str, run_id: str) -> DecisionRunResponse:
        return await self.repository.read_for_user(user_id, run_id)

    async def response_json(self, run_id: str) -> dict[str, object]:
        return (await self.get(run_id)).model_dump(mode="json", by_alias=True)
