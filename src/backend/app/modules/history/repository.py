from __future__ import annotations

import base64
import json

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import AppError
from app.modules.choice.models import PlaceChoice
from app.modules.decision.models import DecisionRun, DiscoverySession, PlaceCandidate
from app.modules.decision.repository.mappers import place_from_candidate, request_for_run
from app.modules.history.schemas import HistoryChoice, HistoryCursor, HistoryItem, HistoryPage


class HistoryRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def list_sessions(self, user_id: str, cursor: HistoryCursor | None, limit: int) -> HistoryPage:
        async with self.sessions() as session:
            query = (
                select(DiscoverySession, PlaceChoice, PlaceCandidate, DecisionRun)
                .join(PlaceChoice, PlaceChoice.discovery_session_id == DiscoverySession.id)
                .join(PlaceCandidate, PlaceChoice.place_candidate_id == PlaceCandidate.id)
                .join(DecisionRun, DecisionRun.id == PlaceCandidate.decision_run_id)
                .where(
                    DiscoverySession.user_id == user_id, PlaceChoice.user_id == user_id,
                    DecisionRun.id == DiscoverySession.current_run_id,
                )
            )
            if cursor is not None:
                timestamp, row_id = cursor
                query = query.where(
                    or_(
                        PlaceChoice.selected_at < timestamp,
                        and_(
                            PlaceChoice.selected_at == timestamp,
                            DiscoverySession.id < row_id,
                        ),
                    )
                )

            sessions = list(
                (
                    await session.execute(
                        # The ID breaks timestamp ties and must match the cursor predicate above.
                        query.order_by(
                            PlaceChoice.selected_at.desc(), DiscoverySession.id.desc()
                        ).limit(limit + 1)
                    )
                ).all()
            )
            page_sessions = sessions[:limit]
            items = [
                HistoryItem(
                    id=row.id,
                    created_at=choice.selected_at,
                    request=request_for_run(run),
                    choice=HistoryChoice(
                        id=choice.id,
                        place=place_from_candidate(candidate),
                        decision_run_id=run.id,
                    ),
                )
                for row, choice, candidate, run in page_sessions
            ]
            next_cursor = None
            if len(sessions) > limit and page_sessions:
                last, choice = page_sessions[-1][0], page_sessions[-1][1]
                next_cursor = base64.urlsafe_b64encode(
                    json.dumps([choice.selected_at.isoformat(), last.id]).encode()
                ).decode()
            return HistoryPage(items=items, next_cursor=next_cursor)

    async def runs(self, user_id: str, session_id: str) -> list[str]:
        async with self.sessions() as session:
            discovery = await session.get(DiscoverySession, session_id)
            if discovery is None or discovery.user_id != user_id:
                raise AppError("NOT_FOUND", "记录不存在", 404)
            return [discovery.current_run_id] if discovery.current_run_id else []
