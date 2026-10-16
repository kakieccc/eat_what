from __future__ import annotations

import base64
import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import AppError
from app.modules.choice.models import PlaceChoice
from app.modules.decision.models import DecisionRun, DiscoverySession, PlaceCandidate
from app.modules.decision.repository.mappers import place_from_candidate, request_for_run
from app.modules.history.schemas import HistoryChoice, HistoryItem, HistoryPage


class HistoryRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def list_sessions(self, user_id: str, cursor: str | None, limit: int) -> HistoryPage:
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
            if cursor:
                try:
                    date_text, row_id = json.loads(base64.urlsafe_b64decode(cursor))
                    timestamp = datetime.fromisoformat(date_text)
                    UUID(row_id)
                    if timestamp.tzinfo is None:
                        raise ValueError
                except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
                    raise AppError("INVALID_CURSOR", "分页参数无效") from None
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
                    request=request_for_run(run, row),
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

    async def ready(self) -> None:
        async with self.sessions() as session:
            await session.execute(select(1))
