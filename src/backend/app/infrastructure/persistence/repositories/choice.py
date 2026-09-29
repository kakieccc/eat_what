from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import now
from app.core.errors import AppError
from app.core.ids import lock_id, request_hash
from app.infrastructure.persistence.models import (
    DecisionRun,
    DiscoverySession,
    IdempotencyRecord,
    PlaceCandidate,
    PlaceChoice,
)
from app.infrastructure.persistence.unit_of_work import UnitOfWork


class ChoiceRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.uow = UnitOfWork(sessions)

    async def choose(
        self,
        user_id: str,
        candidate_id: str,
        feedback: str,
        idempotency_key: str,
    ) -> dict[str, str]:
        body = {"candidate_id": candidate_id, "feedback": feedback}
        async with self.uow.write() as session:
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": lock_id(user_id + idempotency_key + "choice")},
            )
            digest = request_hash(body)
            existing = await session.scalar(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.user_id == user_id,
                    IdempotencyRecord.endpoint == "place-choices",
                    IdempotencyRecord.idempotency_key == idempotency_key,
                )
            )
            if existing:
                if existing.request_hash != digest:
                    raise AppError("IDEMPOTENCY_CONFLICT", "同一标识对应不同选择", 409)
                return {"id": str(existing.response_body["id"]), "candidateId": candidate_id}

            candidate = await session.get(PlaceCandidate, candidate_id)
            if candidate is None:
                raise AppError("NOT_FOUND", "候选不存在", 404)
            run = await session.get(DecisionRun, candidate.decision_run_id)
            if run is None:
                raise AppError("NOT_FOUND", "决策不存在", 404)
            discovery = await session.get(DiscoverySession, run.discovery_session_id)
            if discovery is None or discovery.user_id != user_id:
                raise AppError("NOT_FOUND", "候选不存在", 404)
            if run.status != "completed":
                raise AppError("INVALID_STATE", "决策尚未完成", 409)
            choice = PlaceChoice(
                user_id=user_id,
                discovery_session_id=run.discovery_session_id,
                place_candidate_id=candidate.id,
                feedback=feedback,
                idempotency_key=idempotency_key,
            )
            session.add(choice)
            await session.flush()
            session.add(
                IdempotencyRecord(
                    user_id=user_id,
                    endpoint="place-choices",
                    idempotency_key=idempotency_key,
                    request_hash=digest,
                    response_body={"id": choice.id, "candidateId": candidate.id},
                    expires_at=now() + timedelta(days=7),
                )
            )
            return {"id": choice.id, "candidateId": candidate.id}
