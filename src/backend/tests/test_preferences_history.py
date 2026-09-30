import base64
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.errors import AppError
from app.modules.choice.repository import ChoiceRepository
from app.modules.choice.service import ChoiceService
from app.modules.decision.models import DiscoverySession
from app.modules.history.repository import HistoryRepository
from app.modules.history.service import HistoryService
from app.modules.preferences.repository import PreferencesRepository
from app.modules.preferences.schemas import Budget, Preferences
from app.modules.preferences.service import PreferencesService

pytestmark = pytest.mark.database


async def test_preferences_persist_only_existing_supported_fields(sessions, user_id):
    service = PreferencesService(PreferencesRepository(sessions))
    assert await service.get(user_id) == Preferences()
    submitted = Preferences(
        preferred_cuisines=["面馆"],
        desired_tags=["安静"],
        budget_per_person=Budget(min=10, max=50),
        max_walking_minutes=20,
        party_size=4,
        radius_meters=4000,
        request_text="测试条件",
    )
    assert await service.save(user_id, submitted) == submitted
    saved = await service.get(user_id)
    assert saved == Preferences(
        preferred_cuisines=["面馆"],
        desired_tags=["安静"],
        budget_per_person=Budget(min=10, max=50),
        max_walking_minutes=20,
    )
    assert await service.get(str(uuid4())) == Preferences()


async def test_history_cursor_tie_break_and_ownership(system, sessions, user_id, decision_request):
    history = HistoryService(HistoryRepository(sessions), system.queries)
    choices = ChoiceService(ChoiceRepository(sessions))
    session_ids = []
    for index in range(3):
        run_id = await system.commands.create(
            user_id, decision_request, f"create-{index}", "request"
        )
        claim = await system.tasks.claim(60)
        await system.runner.execute_claim(claim)
        result = await system.queries.get(run_id)
        session_ids.append(result.discovery_session_id)
        await choices.choose(user_id, result.places[0].candidate_id, "", f"choice-{index}")
    async with sessions.begin() as session:
        for discovery in await session.scalars(select(DiscoverySession)):
            discovery.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    first = await history.list_sessions(user_id, None, 2)
    assert first.next_cursor is not None
    second = await history.list_sessions(user_id, first.next_cursor, 2)
    assert second.next_cursor is None
    assert [item.id for item in first.items + second.items] == sorted(session_ids, reverse=True)
    outsider = str(uuid4())
    assert (await history.list_sessions(outsider, None, 20)).items == []
    with pytest.raises(AppError, match="NOT_FOUND"):
        await history.runs(outsider, session_ids[0])
    naive_cursor = base64.urlsafe_b64encode(
        json.dumps(["2026-01-01T00:00:00", session_ids[0]]).encode()
    ).decode()
    with pytest.raises(AppError, match="INVALID_CURSOR"):
        await history.list_sessions(user_id, naive_cursor, 20)
