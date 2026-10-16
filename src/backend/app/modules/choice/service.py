from app.core.errors import AppError
from app.core.ids import request_hash
from app.modules.choice.ports import ChoiceRepository


class ChoiceService:
    def __init__(self, repository: ChoiceRepository) -> None:
        self.repository = repository

    async def choose(self, user_id: str, candidate_id: str, idempotency_key: str) -> dict[str, str]:
        body = {"candidate_id": candidate_id}
        async with self.repository.transaction(user_id, idempotency_key) as tx:
            digest = request_hash(body)
            existing = await tx.idempotency(idempotency_key)
            if existing:
                if existing.request_hash != digest:
                    raise AppError("IDEMPOTENCY_CONFLICT", "请求冲突", 409)
                if existing.response_body.get("superseded"):
                    raise AppError("RUN_SUPERSEDED", "请求冲突", 409)
                await tx.candidate(candidate_id)
                return {"id": str(existing.response_body["id"]), "candidateId": candidate_id}

            candidate = await tx.candidate(candidate_id)
            if candidate.run_status != "completed":
                raise AppError("INVALID_STATE", "请求冲突", 409)
            choice_id = await tx.create_choice(candidate)
            result = {"id": choice_id, "candidateId": candidate.id}
            await tx.record_idempotency(idempotency_key, digest, result)
            return result
