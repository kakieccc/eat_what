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
from app.modules.decision.repository.mappers import place_from_candidate, request_from_session
from app.modules.history.schemas import HistoryChoice, HistoryItem, HistoryPage
from app.modules.preferences.schemas import Preferences


class HistoryRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def list_sessions(self, user_id: str, cursor: str | None, limit: int) -> HistoryPage:
        async with self.sessions() as session:
            query = select(DiscoverySession).where(
                DiscoverySession.user_id == user_id,
                select(PlaceChoice.id)
                .where(
                    PlaceChoice.discovery_session_id == DiscoverySession.id,
                    PlaceChoice.user_id == user_id,
                )
                .exists(),
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
                        DiscoverySession.created_at < timestamp,
                        and_(
                            DiscoverySession.created_at == timestamp,
                            DiscoverySession.id < row_id,
                        ),
                    )
                )

            sessions = list(
                (
                    await session.scalars(
                        query.order_by(
                            DiscoverySession.created_at.desc(), DiscoverySession.id.desc()
                        ).limit(limit + 1)
                    )
                ).all()
            )
            page_sessions = sessions[:limit]
            session_ids = [row.id for row in page_sessions]
            choices = (
                list(
                    (
                        await session.execute(
                            select(PlaceChoice, PlaceCandidate, DecisionRun)
                            .join(
                                PlaceCandidate, PlaceChoice.place_candidate_id == PlaceCandidate.id
                            )
                            .join(DecisionRun, DecisionRun.id == PlaceCandidate.decision_run_id)
                            .where(
                                PlaceChoice.discovery_session_id.in_(session_ids),
                                PlaceChoice.user_id == user_id,
                            )
                            .order_by(PlaceChoice.created_at.desc())
                        )
                    ).all()
                )
                if session_ids
                else []
            )
            items: list[HistoryItem] = []
            for row in page_sessions:
                request = request_from_session(row)
                items.append(
                    HistoryItem(
                        id=row.id,
                        created_at=row.created_at,
                        request=Preferences.model_validate(
                            request.model_dump(exclude={"origin"}, mode="json")
                        ),
                        choices=[
                            HistoryChoice(
                                id=choice.id,
                                feedback=choice.feedback,
                                place=place_from_candidate(candidate),
                                decision_run_id=run.id,
                            )
                            for choice, candidate, run in choices
                            if choice.discovery_session_id == row.id
                        ],
                    )
                )
            next_cursor = None
            if len(sessions) > limit and page_sessions:
                last = page_sessions[-1]
                next_cursor = base64.urlsafe_b64encode(
                    json.dumps([last.created_at.isoformat(), last.id]).encode()
                ).decode()
            return HistoryPage(items=items, next_cursor=next_cursor)

    async def runs(self, user_id: str, session_id: str) -> list[str]:
        async with self.sessions() as session:
            discovery = await session.get(DiscoverySession, session_id)
            if discovery is None or discovery.user_id != user_id:
                raise AppError("NOT_FOUND", "记录不存在", 404)
            return list(
                (
                    await session.scalars(
                        select(DecisionRun.id)
                        .where(DecisionRun.discovery_session_id == session_id)
                        .order_by(DecisionRun.created_at.desc())
                    )
                ).all()
            )

    async def ready(self) -> None:
        async with self.sessions() as session:
            await session.execute(select(1))
