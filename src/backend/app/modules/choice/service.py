from app.core.errors import AppError
from app.core.ids import request_hash
from app.modules.choice.ports import ChoiceRepository


class ChoiceService:
    def __init__(self, repository: ChoiceRepository) -> None:
        self.repository = repository

    async def choose(
        self, user_id: str, candidate_id: str, feedback: str, idempotency_key: str
    ) -> dict[str, str]:
        body = {"candidate_id": candidate_id, "feedback": feedback}
        async with self.repository.transaction(user_id, idempotency_key) as tx:
            digest = request_hash(body)
            existing = await tx.idempotency(idempotency_key)
            if existing:
                if existing.request_hash != digest:
                    raise AppError("IDEMPOTENCY_CONFLICT", "同一标识对应不同选择", 409)
                return {"id": str(existing.response_body["id"]), "candidateId": candidate_id}

            candidate = await tx.candidate(candidate_id)
            if candidate.run_status != "completed":
                raise AppError("INVALID_STATE", "决策尚未完成", 409)
            choice_id = await tx.create_choice(candidate, feedback)
            result = {"id": choice_id, "candidateId": candidate.id}
            await tx.record_idempotency(idempotency_key, digest, result)
            return result
