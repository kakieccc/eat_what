from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import AppError
from app.domain.places.models import Place
from app.infrastructure.persistence.mappers import place_from_candidate
from app.infrastructure.persistence.models import DecisionRun, DiscoverySession, PlaceCandidate
from app.infrastructure.persistence.unit_of_work import UnitOfWork


class PlacesRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.uow = UnitOfWork(sessions)

    async def read(self, user_id: str, place_key: str) -> Place:
        async with self.uow.read() as session:
            candidate = await session.scalar(
                select(PlaceCandidate)
                .join(DecisionRun, DecisionRun.id == PlaceCandidate.decision_run_id)
                .join(DiscoverySession, DiscoverySession.id == DecisionRun.discovery_session_id)
                .where(PlaceCandidate.place_key == place_key, DiscoverySession.user_id == user_id)
                .order_by(PlaceCandidate.created_at.desc())
                .limit(1)
            )
            if candidate is None:
                raise AppError("NOT_FOUND", "地点不存在", 404)
            return place_from_candidate(candidate)
