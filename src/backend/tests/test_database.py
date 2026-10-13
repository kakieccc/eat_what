from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import Connection, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.core.errors import AppError
from app.infrastructure.database.base import Base
from app.infrastructure.database.tables import create_tables
from app.modules.auth.models import User
from app.modules.choice.models import PlaceChoice
from app.modules.choice.repository import ChoiceRepository
from app.modules.choice.service import ChoiceService
from app.modules.decision.models import (
    DecisionRun,
    DiscoverySession,
    IdempotencyRecord,
    PlaceCandidate,
)

pytestmark = pytest.mark.database


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    if not (make_url(url).database or "").endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must point to a database ending in _test")
    schema = f"test_{uuid4().hex}"
    admin = create_async_engine(url)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    try:
        yield scoped
    finally:
        await scoped.dispose()
        try:
            async with admin.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        finally:
            await admin.dispose()


async def test_create_tables_preserves_existing_data(engine: AsyncEngine) -> None:
    await create_tables(engine)
    sessions = async_sessionmaker(engine)
    async with sessions.begin() as session:
        session.add(User(username="schema-test", display_name="Test", password="test-hash"))

    await create_tables(engine)

    async with engine.connect() as connection:
        names = await connection.run_sync(lambda conn: set(inspect(conn).get_table_names()))
        assert names == set(Base.metadata.tables)
        columns = await connection.run_sync(lambda conn: inspect(conn).get_columns("place_choices"))
        assert "idempotency_key" not in {column["name"] for column in columns}
        constraints = await connection.run_sync(
            lambda conn: inspect(conn).get_unique_constraints("place_choices")
        )
        assert constraints == []
        constraints = await connection.run_sync(
            lambda conn: inspect(conn).get_unique_constraints("idempotency_records")
        )
        assert any(
            constraint["column_names"] == ["user_id", "endpoint", "idempotency_key"]
            for constraint in constraints
        )
        assert await connection.scalar(select(func.count()).select_from(User)) == 1


async def test_rebuild_tables_removes_old_schema_and_data(engine: AsyncEngine) -> None:
    await create_tables(engine)
    sessions = async_sessionmaker(engine)
    async with sessions.begin() as session:
        session.add(User(username="old-user", display_name="Test", password="test-hash"))
    async with engine.begin() as connection:
        await connection.execute(text("CREATE TABLE retired_table (id INTEGER PRIMARY KEY)"))
        await connection.execute(text(
            "ALTER TABLE place_choices ADD COLUMN idempotency_key VARCHAR(100) "
            "NOT NULL DEFAULT 'old-key'"
        ))
        await connection.execute(text(
            "ALTER TABLE place_choices ADD UNIQUE (user_id, idempotency_key)"
        ))

    await create_tables(engine, rebuild=True)

    async with engine.connect() as connection:
        names = await connection.run_sync(lambda conn: set(inspect(conn).get_table_names()))
        assert names == set(Base.metadata.tables)
        columns = await connection.run_sync(lambda conn: inspect(conn).get_columns("place_choices"))
        assert "idempotency_key" not in {column["name"] for column in columns}
        assert await connection.scalar(select(func.count()).select_from(User)) == 0


async def test_rebuild_failure_rolls_back_deleted_data(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch,
) -> None:
    await create_tables(engine)
    sessions = async_sessionmaker(engine)
    async with sessions.begin() as session:
        session.add(User(username="retained-user", display_name="Test", password="test-hash"))

    def fail_create(connection: Connection) -> None:
        raise RuntimeError("Creation failed")

    monkeypatch.setattr(Base.metadata, "create_all", fail_create)
    with pytest.raises(RuntimeError, match="Creation failed"):
        await create_tables(engine, rebuild=True)

    async with engine.connect() as connection:
        assert await connection.scalar(select(func.count()).select_from(User)) == 1


async def test_choice_retries_share_one_record_and_reject_changed_content(
    engine: AsyncEngine,
) -> None:
    await create_tables(engine)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions.begin() as session:
        user = User(username="choice-test", display_name="Test", password="test-hash")
        session.add(user)
        await session.flush()
        discovery = DiscoverySession(
            user_id=user.id, origin_latitude=31.2, origin_longitude=121.5,
            radius_meters=2000, meal_period="lunch", party_size=1,
        )
        session.add(discovery)
        await session.flush()
        run = DecisionRun(discovery_session_id=discovery.id, status="completed")
        session.add(run)
        await session.flush()
        candidate = PlaceCandidate(
            decision_run_id=run.id, place_key="test-place", external_place_id="test-place",
            name="Test place", latitude=31.2, longitude=121.5,
            straight_line_distance_meters=100, rank=1,
        )
        session.add(candidate)
        await session.flush()

    service = ChoiceService(ChoiceRepository(sessions))
    first, retry = await asyncio.gather(
        service.choose(user.id, candidate.id, "", "test-choice-key"),
        service.choose(user.id, candidate.id, "", "test-choice-key"),
    )
    assert first == retry
    with pytest.raises(AppError) as error:
        await service.choose(user.id, candidate.id, "changed", "test-choice-key")
    assert error.value.code == "IDEMPOTENCY_CONFLICT"
    assert error.value.status == 409
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(PlaceChoice)) == 1
        assert await session.scalar(select(func.count()).select_from(IdempotencyRecord)) == 1
