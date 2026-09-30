from __future__ import annotations

import os
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.infrastructure.persistence.base import Base
from app.infrastructure.persistence.registry import register_models
from app.modules.auth.models import User
from app.modules.decision.repository.repository import DecisionRepository
from app.modules.decision.schemas import DecisionRequest, Intent
from app.modules.decision.service.commands import DecisionCommandService
from app.modules.decision.service.queries import DecisionQueryService
from app.modules.decision.service.runner import DecisionRunner
from app.modules.location.schemas import Origin, Point
from app.modules.places.schemas import Place, Route
from app.modules.task.repository import TaskStore


@pytest.fixture
async def sessions():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    database = make_url(url).database or ""
    if not database.endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must point to an isolated database ending in _test")
    schema = f"refactor_{uuid4().hex}"
    admin = create_async_engine(url, poolclass=NullPool)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        url,
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": schema}},
    )
    try:
        register_models()
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


@pytest.fixture
async def user_id(sessions):
    async with sessions.begin() as session:
        user = User(username="tester", display_name="Tester", password="unused")
        session.add(user)
        await session.flush()
        return user.id


@pytest.fixture
def decision_request():
    return DecisionRequest(origin=Origin(latitude=31.23, longitude=121.47, address="上海"))


@pytest.fixture
def place():
    return Place(
        id="amap:restaurant",
        external_id="restaurant",
        name="面馆",
        category_code="050000",
        category_name="餐饮",
        cuisine_types=["面馆"],
        address="测试地址",
        location=Point(latitude=31.231, longitude=121.471),
        straight_line_distance_meters=150,
        rating=4.5,
        average_cost=25,
        business_status="open",
        data_updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


@pytest.fixture
def providers(place, decision_request):
    route = Route(distance_meters=200, duration_seconds=180, polyline=[])
    amap = SimpleNamespace(
        search=AsyncMock(return_value=[place]),
        detail=AsyncMock(return_value=place),
        walking=AsyncMock(return_value=route),
        reverse=AsyncMock(return_value=decision_request.origin),
        tips=AsyncMock(return_value=[decision_request.origin]),
        navigation=lambda origin, selected: "https://uri.amap.com/navigation?test=1",
    )
    llm = SimpleNamespace(
        parse_intent=AsyncMock(return_value=Intent()),
        rerank=AsyncMock(side_effect=lambda places, preferences: places),
        explain=AsyncMock(side_effect=lambda places: places),
    )
    return SimpleNamespace(amap=amap, llm=llm)


@pytest.fixture
def system(sessions, providers):
    repository = DecisionRepository(sessions, "test-model")
    tasks = TaskStore(sessions)
    queries = DecisionQueryService(repository)
    runner = DecisionRunner(repository, tasks, queries, providers.amap, providers.llm, 60, 20)
    return SimpleNamespace(
        repository=repository,
        tasks=tasks,
        queries=queries,
        runner=runner,
        commands=DecisionCommandService(repository),
    )


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://test@localhost/eat_what_test",
        amap_web_service_key="test-amap",
        llm_api_key="test-key",
        llm_base_url="https://example.invalid/v1",
        llm_model="test-model",
    )
