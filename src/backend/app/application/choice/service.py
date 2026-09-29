from app.application.choice.ports import ChoiceRepository


class ChoiceService:
    def __init__(self, repository: ChoiceRepository) -> None:
        self.repository = repository

    async def choose(
        self, user_id: str, candidate_id: str, feedback: str, idempotency_key: str
    ) -> dict[str, str]:
        return await self.repository.choose(user_id, candidate_id, feedback, idempotency_key)
