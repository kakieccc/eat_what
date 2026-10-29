import asyncio
import unittest
from datetime import timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.clock import now
from app.core.config import Settings
from app.infrastructure.database.metadata import metadata
from app.modules.auth.models import User
from app.modules.choice.models import PlaceChoice
from app.modules.decision.models import DecisionRun, DiscoverySession, PlaceCandidate
from app.modules.decision.schemas import DecisionRequest
from app.modules.location.schemas import Origin, Point
from app.modules.places.schemas import Place
from app.modules.preferences import batch
from app.modules.preferences.models import Preference, PreferenceSample
from app.modules.preferences.repository import PreferencesRepository, record_meal
from app.modules.preferences.schemas import (
    AccountPreferences,
    LearnedPreferences,
    LearnedRadius,
    PrefillSnapshot,
)


def learned(schema, prompt, data):
    return LearnedPreferences(budget_per_person=[], soft_preferences=[], radius_meters=[
        LearnedRadius(value=2000, sample_ids=[meal["sample_id"] for meal in data["meals"][:3]]),
    ])


class CommandTests(unittest.TestCase):
    def test_exit_status_reports_learning_failures_and_sanitizes_errors(self):
        with patch("sys.argv", ["preference-batch"]):
            for success in (True, False):
                with patch.object(batch, "run", new_callable=AsyncMock, return_value=success):
                    self.assertEqual(batch.main(), 0 if success else 1)
            with patch.object(batch, "run", side_effect=RuntimeError("private provider data")):
                with self.assertLogs("food.preferences", level="ERROR") as logs:
                    self.assertEqual(batch.main(), 1)
                self.assertNotIn("private provider data", "".join(logs.output))


class PreferenceBatchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.schema = "test_preference_batch_" + uuid4().hex
        self.engine = create_async_engine(Settings().db_url, connect_args={
            "server_settings": {"search_path": self.schema},
        })
        self.addAsyncCleanup(self.cleanup_schema)
        async with self.engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))
            await connection.run_sync(metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.repository = PreferencesRepository(self.sessions)
        self.llm = AsyncMock()
        self.llm.structured.side_effect = learned
        self.user_id = await self.user("first")

    async def cleanup_schema(self):
        try:
            async with self.engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE'))
        finally:
            await self.engine.dispose()

    async def user(self, name):
        async with self.sessions.begin() as session:
            row = User(username=name, display_name=name, password="test-hash")
            session.add(row)
            await session.flush()
            return row.id

    async def meals(self, count, user_id=None):
        user_id = user_id or self.user_id
        request = DecisionRequest(origin=Origin(latitude=31.23, longitude=121.47))
        prefill = PrefillSnapshot(values=AccountPreferences(radius_meters=1000), source="defaults")
        place = Place(id="place", external_id="poi", name="Test restaurant", category_code="050000",
                      category_name="中餐厅", cuisine_types=["中餐"], address="Test address",
                      location=Point(latitude=31.23, longitude=121.47), straight_line_distance_meters=0,
                      data_updated_at=now())
        async with self.sessions.begin() as session:
            for _ in range(count):
                discovery = DiscoverySession(user_id=user_id, request_snapshot=request.model_dump(mode="json"),
                                             prefill_snapshot=prefill.model_dump(mode="json"))
                session.add(discovery)
                await session.flush()
                run = DecisionRun(discovery_session_id=discovery.id, status="completed",
                                  effective_preferences=request.model_dump(mode="json"))
                session.add(run)
                await session.flush()
                discovery.current_run_id = run.id
                candidate = PlaceCandidate(decision_run_id=run.id, place_key=place.id, rank=1,
                                           place_snapshot=place.model_dump(mode="json"))
                session.add(candidate)
                await session.flush()
                choice = PlaceChoice(user_id=user_id, discovery_session_id=discovery.id,
                                     place_candidate_id=candidate.id)
                session.add(choice)
                await session.flush()
                await record_meal(session, user_id, choice.id, candidate.id)

    async def preference(self, user_id=None):
        async with self.sessions() as session:
            return await session.scalar(select(Preference).where(Preference.user_id == (user_id or self.user_id)))

    async def test_empty_batch_and_ten_then_five_meal_thresholds(self):
        self.assertEqual(await batch.run_batch(self.sessions, self.llm, 60),
                         {"succeeded": 0, "failed": 0, "skipped": 0})
        await self.meals(9)
        self.assertEqual((await batch.run_batch(self.sessions, self.llm, 60))["succeeded"], 0)
        self.llm.structured.assert_not_awaited()
        await self.meals(1)
        self.assertEqual((await batch.run_batch(self.sessions, self.llm, 60))["succeeded"], 1)
        await self.meals(4)
        self.assertEqual((await batch.run_batch(self.sessions, self.llm, 60))["succeeded"], 0)
        await self.meals(1)
        self.assertEqual((await batch.run_batch(self.sessions, self.llm, 60))["succeeded"], 1)
        self.assertEqual(self.llm.structured.await_count, 2)

    async def test_coalesces_triggers_uses_twenty_samples_and_preserves_manual_values(self):
        await self.meals(25)
        async with self.sessions.begin() as session:
            row = await session.scalar(select(Preference).where(Preference.user_id == self.user_id))
            row.overrides = {"radius_meters": 500}
        self.assertEqual((await batch.run_batch(self.sessions, self.llm, 60))["succeeded"], 1)
        self.llm.structured.assert_awaited_once()
        self.assertEqual(len(self.llm.structured.call_args.args[2]["meals"]), 20)
        row = await self.preference()
        self.assertEqual((row.attempted_count, row.learning_status, row.revision), (25, "idle", 1))
        self.assertEqual(row.learned["radius_meters"][0]["value"], 2000)
        effective = await self.repository.get(self.user_id)
        self.assertEqual(effective.defaults.radius_meters, 500)
        self.assertEqual(effective.sources["radiusMeters"], "manual")
        self.assertEqual((await batch.run_batch(self.sessions, self.llm, 60))["succeeded"], 0)

    async def test_new_triggers_and_users_wait_until_the_next_batch(self):
        await self.meals(10)
        other = await self.user("second")

        async def during_learning(schema, prompt, data):
            await self.meals(5)
            await self.meals(10, other)
            return learned(schema, prompt, data)

        self.llm.structured.side_effect = during_learning
        self.assertEqual((await batch.run_batch(self.sessions, self.llm, 60))["succeeded"], 1)
        self.llm.structured.assert_awaited_once()
        row = await self.preference()
        self.assertEqual((row.attempted_count, row.requested_count, row.learning_status), (10, 15, "queued"))
        self.llm.structured.side_effect = learned
        self.assertEqual((await batch.run_batch(self.sessions, self.llm, 60))["succeeded"], 2)

    async def test_one_failure_keeps_old_preferences_and_does_not_stop_other_users(self):
        await self.meals(10)
        other = await self.user("second")
        await self.meals(10, other)
        old = LearnedPreferences(budget_per_person=[], soft_preferences=[], radius_meters=[
            LearnedRadius(value=1000, sample_ids=["old-1", "old-2", "old-3"]),
        ]).model_dump(mode="json")
        async with self.sessions.begin() as session:
            row = await session.scalar(select(Preference).where(Preference.user_id == self.user_id))
            row.learned = old
        async with self.sessions() as session:
            failing_samples = set((await session.scalars(
                select(PreferenceSample.id).where(PreferenceSample.user_id == self.user_id)
            )).all())

        async def sometimes_fail(schema, prompt, data):
            if data["meals"][0]["sample_id"] in failing_samples:
                raise RuntimeError("provider failed")
            return learned(schema, prompt, data)

        self.llm.structured.side_effect = sometimes_fail
        self.assertEqual(await batch.run_batch(self.sessions, self.llm, 60),
                         {"succeeded": 1, "failed": 1, "skipped": 0})
        row = await self.preference()
        self.assertEqual((row.learning_status, row.learned, row.attempted_count), ("failed", old, 10))

    async def test_expired_lease_is_recovered_and_heartbeats_are_preserved(self):
        await self.meals(10)
        async with self.sessions.begin() as session:
            row = await session.scalar(select(Preference).where(Preference.user_id == self.user_id))
            row.learning_status = "running"
            row.lease_token = "old-token"
            row.lease_until = now() - timedelta(seconds=1)
        heartbeat = asyncio.Event()
        original = PreferencesRepository.renew

        async def renew(repository, claim, lease_seconds):
            await original(repository, claim, lease_seconds)
            heartbeat.set()

        async def wait_for_heartbeat(schema, prompt, data):
            await asyncio.wait_for(heartbeat.wait(), timeout=3)
            return learned(schema, prompt, data)

        self.llm.structured.side_effect = wait_for_heartbeat
        with patch.object(PreferencesRepository, "renew", new=renew):
            self.assertEqual((await batch.run_batch(self.sessions, self.llm, 3))["succeeded"], 1)
        self.assertIsNone((await self.preference()).lease_token)

    async def test_active_lease_is_skipped_and_lost_lease_cannot_overwrite_result(self):
        await self.meals(10)
        row = await self.preference()
        claim = await self.repository.claim(60, preference_id=row.id)
        self.assertIsNotNone(claim)
        self.assertEqual((await batch.run_batch(self.sessions, self.llm, 60))["succeeded"], 0)
        self.llm.structured.assert_not_awaited()
        async with self.sessions.begin() as session:
            row = await session.get(Preference, row.id)
            row.lease_until = now() - timedelta(seconds=1)

        async def lose_lease(schema, prompt, data):
            async with self.sessions.begin() as session:
                row = await session.scalar(select(Preference).where(Preference.user_id == self.user_id))
                row.lease_token = "another-owner"
            return learned(schema, prompt, data)

        self.llm.structured.side_effect = lose_lease
        self.assertEqual(await batch.run_batch(self.sessions, self.llm, 60),
                         {"succeeded": 0, "failed": 0, "skipped": 1})
        self.assertFalse((await self.preference()).learned)

    async def test_overlapping_batch_is_skipped_and_the_global_lock_is_released(self):
        await self.meals(10)
        started, resume = asyncio.Event(), asyncio.Event()

        async def paused(schema, prompt, data):
            started.set()
            await resume.wait()
            return learned(schema, prompt, data)

        self.llm.structured.side_effect = paused
        first = asyncio.create_task(batch.run_batch(self.sessions, self.llm, 60))
        try:
            await asyncio.wait_for(started.wait(), timeout=3)
            with self.assertLogs("food.preferences", level="INFO") as logs:
                self.assertEqual(await batch.run_batch(self.sessions, self.llm, 60),
                                 {"succeeded": 0, "failed": 0, "skipped": 0})
            self.assertIn("alreadyRunning", "".join(logs.output))
        finally:
            resume.set()
            await asyncio.wait_for(first, timeout=5)
        self.llm.structured.assert_awaited_once()
        self.assertEqual((await batch.run_batch(self.sessions, self.llm, 60))["succeeded"], 0)


if __name__ == "__main__":
    unittest.main()
