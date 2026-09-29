from typing import Protocol


class ChoiceRepository(Protocol):
    async def choose(
        self, user_id: str, candidate_id: str, feedback: str, idempotency_key: str
    ) -> dict[str, str]: ...
