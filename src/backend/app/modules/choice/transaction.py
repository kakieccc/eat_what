from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now
from app.core.errors import AppError
from app.modules.choice.models import PlaceChoice
from app.modules.choice.ports import CandidateSnapshot, IdempotencySnapshot
from app.modules.decision.models import (
    DecisionRun,
    DiscoverySession,
    IdempotencyRecord,
    PlaceCandidate,
)


class ChoiceTransaction:
    def __init__(self, session: AsyncSession, user_id: str) -> None:
        self.session = session
        self.user_id = user_id

    async def idempotency(self, key: str) -> IdempotencySnapshot | None:
        row = await self.session.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.user_id == self.user_id,
                IdempotencyRecord.endpoint == "place-choices",
                IdempotencyRecord.idempotency_key == key,
            )
        )
        return IdempotencySnapshot(row.request_hash, dict(row.response_body)) if row else None

    async def candidate(self, candidate_id: str) -> CandidateSnapshot:
        candidate = await self.session.get(PlaceCandidate, candidate_id)
        if candidate is None:
            raise AppError("NOT_FOUND", "候选不存在", 404)
        run = await self.session.get(DecisionRun, candidate.decision_run_id)
        if run is None:
            raise AppError("NOT_FOUND", "决策不存在", 404)
        discovery = await self.session.get(DiscoverySession, run.discovery_session_id)
        if discovery is None or discovery.user_id != self.user_id:
            raise AppError("NOT_FOUND", "候选不存在", 404)
        return CandidateSnapshot(candidate.id, run.discovery_session_id, run.status)

    async def create_choice(
        self, candidate: CandidateSnapshot, feedback: str, key: str
    ) -> str:
        choice = PlaceChoice(
            user_id=self.user_id,
            discovery_session_id=candidate.discovery_session_id,
            place_candidate_id=candidate.id,
            feedback=feedback,
            idempotency_key=key,
        )
        self.session.add(choice)
        await self.session.flush()
        return choice.id

    async def record_idempotency(
        self, key: str, digest: str, result: dict[str, str]
    ) -> None:
        self.session.add(
            IdempotencyRecord(
                user_id=self.user_id,
                endpoint="place-choices",
                idempotency_key=key,
                request_hash=digest,
                response_body=dict(result),
                expires_at=now() + timedelta(days=7),
            )
        )
