from datetime import timedelta

from sqlalchemy import delete, select
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
from app.modules.preferences.repository import record_meal


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
        current = now()
        if row and row.expires_at <= current:
            await self.session.execute(delete(IdempotencyRecord).where(
                IdempotencyRecord.id == row.id, IdempotencyRecord.expires_at <= current,
            ))
            await self.session.flush()
            return None
        return IdempotencySnapshot(row.request_hash, dict(row.response_body)) if row else None

    async def candidate(self, candidate_id: str) -> CandidateSnapshot:
        candidate = await self.session.get(PlaceCandidate, candidate_id)
        if candidate is None:
            raise AppError("NOT_FOUND", "候选不存在", 404)
        run = await self.session.get(DecisionRun, candidate.decision_run_id)
        if run is None:
            raise AppError("NOT_FOUND", "决策不存在", 404)
        # Share this lock with refinement so choosing and replacing candidates cannot both win.
        discovery = await self.session.scalar(
            select(DiscoverySession)
            .where(
                DiscoverySession.id == run.discovery_session_id,
                DiscoverySession.user_id == self.user_id,
            )
            .with_for_update()
        )
        if discovery is None:
            raise AppError("NOT_FOUND", "候选不存在", 404)
        if discovery.current_run_id != run.id:
            raise AppError("RUN_SUPERSEDED", "请求冲突", 409)
        return CandidateSnapshot(candidate.id, run.discovery_session_id, run.status)

    async def create_choice(self, candidate: CandidateSnapshot) -> str:
        choice = await self.session.scalar(
            select(PlaceChoice)
            .where(PlaceChoice.discovery_session_id == candidate.discovery_session_id)
            .with_for_update()
        )
        if choice is not None:
            if choice.place_candidate_id != candidate.id:
                raise AppError("SELECTION_COMPLETED", "本次选餐已结束，请开始新的选餐", 409)
            return choice.id
        choice = PlaceChoice(
            user_id=self.user_id,
            discovery_session_id=candidate.discovery_session_id,
            place_candidate_id=candidate.id,
        )
        self.session.add(choice)
        await self.session.flush()
        # The saved choice and its learning evidence must commit or roll back together.
        await record_meal(self.session, self.user_id, choice.id, candidate.id)
        return choice.id

    async def record_idempotency(self, key: str, digest: str, result: dict[str, str]) -> None:
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
