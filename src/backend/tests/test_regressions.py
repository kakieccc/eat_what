import asyncio
import json
import unittest
from contextlib import nullcontext
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
from fastapi import FastAPI, Request
from pydantic import ValidationError
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.errors import register_exception_handlers
from app.bootstrap import lifespan
from app.core.clock import now
from app.core.config import Settings
from app.infrastructure.amap.cache import AmapCache
from app.infrastructure.amap.provider import AmapGeoPlaceProvider
from app.infrastructure.amap.schemas import FetchedResponse
from app.infrastructure.database.metadata import metadata
from app.modules.auth.models import User
from app.modules.decision.models import DecisionRun, DiscoverySession
from app.modules.decision.repository.repository import DecisionRepository
from app.modules.decision.schemas import DecisionRequest
from app.modules.decision.workflow.events import NodeCompleted
from app.modules.decision.workflow.nodes.search_places import build
from app.modules.location.schemas import Origin
from app.modules.places.service import PlaceService
from app.modules.preferences.schemas import (
    AccountPreferences,
    Budget,
    PreferenceOverrides,
    Preferences,
    PrefillSnapshot,
)
from app.modules.task.errors import LostTaskLease
from app.modules.task.models import Task, TaskStep
from app.modules.task.repository import TaskStore
from app.modules.task.types import TaskClaim


class LifespanTests(unittest.IsolatedAsyncioTestCase):
    async def test_shutdown_cleans_resources_and_does_not_hide_worker_failures(self):
        for failed in (False, True):
            with self.subTest(failed=failed):
                started = asyncio.Event()

                async def run(started=started, failed=failed):
                    started.set()
                    if failed:
                        raise RuntimeError("worker failed")
                    await asyncio.Future()

                passwords = SimpleNamespace(aclose=AsyncMock())
                engine = SimpleNamespace(dispose=AsyncMock())
                services = SimpleNamespace(worker=SimpleNamespace(run=run),
                                           auth=SimpleNamespace(passwords=passwords))
                app = FastAPI()
                app.state.settings = Settings()
                with patch("app.bootstrap.create_sessions"), \
                        patch("app.bootstrap.engine_of", return_value=engine), \
                        patch("app.bootstrap.httpx.AsyncClient"), \
                        patch("app.bootstrap.AsyncOpenAI"), \
                        patch("app.bootstrap.build_container", return_value=services):
                    with self.assertRaisesRegex(RuntimeError, "worker failed") if failed else nullcontext():
                        async with lifespan(app):
                            await asyncio.wait_for(started.wait(), timeout=1)
                passwords.aclose.assert_awaited_once()
                engine.dispose.assert_awaited_once()
                self.assertFalse(app.state.ready)


class PreferenceContractTests(unittest.TestCase):
    def test_stored_preferences_and_overrides_follow_the_current_food_limit(self):
        foods = [f"food-{index}" for index in range(6)]
        for schema in (Preferences, AccountPreferences, PreferenceOverrides):
            with self.subTest(schema=schema.__name__):
                self.assertEqual(schema(allowed_foods=foods[:5]).allowed_foods, foods[:5])
                with self.assertRaises(ValidationError):
                    schema(allowed_foods=foods)

    def test_budget_precision_is_the_same_for_requests_defaults_and_snapshots(self):
        self.assertEqual(Budget(min="20.50").model_dump(mode="json")["min"], "20.5")
        for schema in (Preferences, AccountPreferences, PreferenceOverrides):
            with self.subTest(schema=schema.__name__):
                with self.assertRaises(ValidationError):
                    schema(budget_per_person={"min": "20.501"})
        with self.assertRaises(ValidationError):
            PrefillSnapshot.model_validate({
                "values": {"budget_per_person": {"min": "20.501"}}, "source": "history",
            })


class SearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_pagination_survives_filtering_deduplication_and_cache_hits(self):
        origin = Origin(latitude=31.23, longitude=121.47)
        request = DecisionRequest(
            origin=origin, preferences={"budget_per_person": {"min": 20, "max": 60}}
        )

        def raw(index, cost):
            return {"id": str(index), "name": f"place-{index}",
                    "location": "121.47,31.23", "biz_ext": {"cost": str(cost)}}

        for last in ({"id": "bad", "name": "bad", "location": "bad"}, raw(0, 100)):
            for cached in (False, True):
                with self.subTest(last=last["id"], cached=cached):
                    pages = [
                        FetchedResponse(payload={"status": "1", "pois": [
                            *(raw(i, 100) for i in range(24)), last,
                        ]}, fetched_at=now()),
                        FetchedResponse(payload={"status": "1", "pois": [
                            raw(i, 30) for i in range(25, 28)
                        ]}, fetched_at=now()),
                    ]
                    cache = SimpleNamespace(
                        key=AmapCache.key,
                        read=AsyncMock(side_effect=[pages[0], None, None] if cached else [None] * 4),
                        write=AsyncMock(),
                    )
                    client = SimpleNamespace(request=AsyncMock(side_effect=pages[1:] if cached else pages))
                    provider = AmapGeoPlaceProvider(client, cache, 10)
                    service = PlaceService(SimpleNamespace(), provider, 10)
                    result = await build(service)({
                        "request": request.model_dump(mode="json"), "places": [],
                        "excluded": [], "filter_summary": {},
                    })
                    self.assertEqual(len(result["places"]), 3)
                    self.assertEqual(result["filter_summary"]["searchRequests"], 2)
                    self.assertFalse(result["search_queue"])


class ErrorTests(unittest.IsolatedAsyncioTestCase):
    async def test_database_log_keeps_diagnostics_without_sql_or_secrets(self):
        class DriverError(Exception):
            sqlstate = "42P01"

        app = FastAPI()
        register_exception_handlers(app)

        @app.get("/failure")
        async def failure(request: Request):
            request.state.request_id = "request-123"
            raise DBAPIError("SELECT private_sql", {"password": "private_bind"}, DriverError("private_driver"))

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            with self.assertLogs("food", level="ERROR") as logs:
                response = await client.get("/failure")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["meta"]["requestId"], "request-123")
        entry = json.loads(logs.records[0].getMessage())
        self.assertEqual(entry["sqlstate"], "42P01")
        self.assertEqual(entry["requestId"], "request-123")
        self.assertNotIn("private_", logs.output[0])


class TaskEventTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.schema = "test_task_events_" + uuid4().hex
        self.engine = create_async_engine(Settings().db_url, connect_args={
            "server_settings": {"search_path": self.schema},
        })
        self.addAsyncCleanup(self.cleanup_schema)
        async with self.engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))
            await connection.run_sync(metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.store = TaskStore(self.sessions)
        self.repository = DecisionRepository(self.sessions, "test-model")
        async with self.sessions.begin() as session:
            user = User(username="test", display_name="Test", password="test-hash")
            session.add(user)
            await session.flush()
            discovery = DiscoverySession(
                user_id=user.id, request_snapshot={},
                prefill_snapshot=PrefillSnapshot(values=AccountPreferences(), source="defaults").model_dump(mode="json"),
            )
            session.add(discovery)
            await session.flush()
            run = DecisionRun(discovery_session_id=discovery.id, status="running")
            session.add(run)
            await session.flush()
            discovery.current_run_id = run.id
            task = Task(decision_run_id=run.id, status="running", lease_token="old-token",
                        lease_until=now() + timedelta(seconds=60), started_at=now())
            session.add(task)
            await session.flush()
            session.add(TaskStep(task_id=task.id, key="search", ordinal=0, status="running"))
            self.run_id = run.id
            self.claim = TaskClaim(task.id, "old-token")
        self.event = NodeCompleted(node="search", duration_ms=1, output_count=0)

    async def cleanup_schema(self):
        try:
            async with self.engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE'))
        finally:
            await self.engine.dispose()

    async def test_expired_replaced_and_terminal_claims_cannot_append_events(self):
        await self.store.append_event(self.claim, self.event)
        async with self.sessions.begin() as session:
            await session.execute(update(Task).where(Task.id == self.claim.task_id).values(
                lease_until=now() - timedelta(seconds=1),
            ))
        with self.assertRaises(LostTaskLease):
            await self.store.append_event(self.claim, self.event)
        with self.assertRaises(LostTaskLease):
            await self.store.renew(self.claim, 60)
        current = await self.store.claim(60)
        self.assertIsNotNone(current)
        with self.assertRaises(LostTaskLease):
            await self.store.append_event(self.claim, self.event)
        await self.store.append_event(current, self.event)
        for status in ("succeeded", "failed", "superseded"):
            async with self.sessions.begin() as session:
                await session.execute(update(Task).where(Task.id == current.task_id).values(status=status))
            with self.assertRaises(LostTaskLease):
                await self.store.append_event(current, self.event)
        self.assertEqual(len(await self.store.events(self.claim.task_id)), 2)

    async def test_concurrent_events_get_unique_ordered_sequences(self):
        await asyncio.gather(*(self.store.append_event(self.claim, self.event) for _ in range(5)))
        self.assertEqual([event.sequence for event in await self.store.events(self.claim.task_id)], [1, 2, 3, 4, 5])

    async def test_failure_and_its_event_commit_or_roll_back_together(self):
        with patch("app.modules.decision.repository.repository.record_event", side_effect=RuntimeError("event failed")):
            with self.assertRaises(RuntimeError):
                await self.repository.fail(self.claim, "LLM_UNAVAILABLE", "Unavailable", True)
        async with self.sessions() as session:
            task = await session.get(Task, self.claim.task_id)
            run = await session.get(DecisionRun, self.run_id)
            self.assertEqual((task.status, task.lease_token, run.status), ("running", "old-token", "running"))
        self.assertFalse(await self.store.events(self.claim.task_id))
        self.assertTrue(await self.repository.fail(self.claim, "LLM_UNAVAILABLE", "Unavailable", True))
        events = await self.store.events(self.claim.task_id)
        self.assertEqual(events[0].payload["type"], "runFailed")
        self.assertTrue(events[0].payload["error"]["retryable"])
        async with self.sessions() as session:
            task = await session.get(Task, self.claim.task_id)
            run = await session.get(DecisionRun, self.run_id)
            step = await session.scalar(select(TaskStep).where(TaskStep.task_id == task.id))
            self.assertEqual((task.status, run.status, step.status), ("failed", "failed", "failed"))
            self.assertIsNone(task.lease_token)
        self.assertFalse(await self.repository.fail(self.claim, "INTERNAL_ERROR", "Late failure", False))
        self.assertEqual(len(await self.store.events(self.claim.task_id)), 1)


if __name__ == "__main__":
    unittest.main()
