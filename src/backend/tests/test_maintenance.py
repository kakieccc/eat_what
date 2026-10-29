import asyncio
import json
import unittest
from datetime import timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from alembic.config import Config
from sqlalchemy import func, insert, inspect, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.sql.dml import Delete, Insert

from alembic import command
from app import maintenance
from app.core.clock import now
from app.core.config import Settings
from app.core.errors import AppError
from app.infrastructure.amap.cache import AmapCache
from app.infrastructure.amap.models import PlaceCache
from app.infrastructure.amap.schemas import FetchedResponse
from app.infrastructure.database.metadata import metadata
from app.modules.auth.models import AuthRateLimit, AuthSession, User
from app.modules.auth.repository import SqlAuthRepository
from app.modules.choice.models import PlaceChoice
from app.modules.choice.repository import ChoiceRepository
from app.modules.choice.service import ChoiceService
from app.modules.decision.models import (
    DecisionRun,
    DiscoverySession,
    IdempotencyRecord,
    PlaceCandidate,
)
from app.modules.decision.repository.repository import DecisionRepository
from app.modules.decision.schemas import DecisionCreateRequest
from app.modules.decision.service.commands import DecisionCommandService
from app.modules.decision.workflow.state import SCHEMA_VERSION
from app.modules.location.schemas import Origin
from app.modules.places.schemas import Place
from app.modules.preferences.models import Preference, PreferenceSample
from app.modules.preferences.schemas import AccountPreferences, PrefillSnapshot
from app.modules.task.models import Task, TaskEvent, TaskStep


class CommandTests(unittest.TestCase):
    def test_dry_run_flag_and_nonzero_failure_exit_do_not_expose_error_text(self):
        with patch("sys.argv", ["maintenance", "--dry-run"]):
            with patch.object(maintenance, "run", new_callable=AsyncMock) as run:
                self.assertEqual(maintenance.main(), 0)
                run.assert_awaited_once_with(True)
            with patch.object(maintenance, "run", side_effect=RuntimeError("private credential")):
                with self.assertLogs("food.maintenance", level="ERROR") as logs:
                    self.assertEqual(maintenance.main(), 1)
                self.assertNotIn("private credential", "".join(logs.output))


class MaintenanceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.cutoff = now()
        self.schema = "test_maintenance_" + uuid4().hex
        self.engine = create_async_engine(Settings().db_url, connect_args={
            "server_settings": {"search_path": self.schema},
        })
        self.addAsyncCleanup(self.cleanup_schema)
        async with self.engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))
            await connection.run_sync(metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.sessions.begin() as session:
            user = User(username="test", display_name="Test", password="test-hash")
            session.add(user)
            await session.flush()
            self.user_id = user.id

    async def cleanup_schema(self):
        try:
            async with self.engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE'))
        finally:
            await self.engine.dispose()

    async def sweep(self, *, dry_run=False, sessions=None):
        with patch.object(maintenance, "now", return_value=self.cutoff):
            return await maintenance.cleanup(sessions or self.sessions, dry_run=dry_run)

    async def seed_temporary(self):
        async with self.sessions.begin() as session:
            for index, delta in enumerate((-1, 0, 3600)):
                expiry = self.cutoff + timedelta(seconds=delta)
                session.add_all([
                    PlaceCache(cache_key=f"cache-{index}", payload={"private": "cache"}, expires_at=expiry),
                    AuthSession(user_id=self.user_id, token_hash=f"token-{index}", csrf_token="private", expires_at=expiry),
                    IdempotencyRecord(user_id=self.user_id, endpoint="test", idempotency_key=f"key-{index}",
                                      request_hash="digest", response_body={"private": "body"}, expires_at=expiry),
                    AuthRateLimit(key_hash=f"rate-{index}", window_started_at=expiry - timedelta(hours=24), attempts=1),
                ])

    async def table_counts(self):
        async with self.sessions() as session:
            return {name: await session.scalar(select(func.count()).select_from(table))
                    for name, table in metadata.tables.items()}

    async def candidate(self):
        request = DecisionCreateRequest(
            origin=Origin(latitude=31.23, longitude=121.47),
            prefill_snapshot=PrefillSnapshot(values=AccountPreferences(), source="defaults"),
        )
        snapshot = request.model_dump(mode="json", exclude={"prefill_snapshot"})
        async with self.sessions.begin() as session:
            discovery = DiscoverySession(
                user_id=self.user_id, request_snapshot=snapshot,
                prefill_snapshot=request.prefill_snapshot.model_dump(mode="json"),
            )
            session.add(discovery)
            await session.flush()
            run = DecisionRun(discovery_session_id=discovery.id, status="completed",
                              original_request=snapshot, effective_preferences=snapshot)
            session.add(run)
            await session.flush()
            discovery.current_run_id = run.id
            place = Place(
                id=str(uuid4()), external_id="test", name="Test", category_code="050000",
                category_name="餐饮服务", cuisine_types=[], address="Test", location=request.origin,
                straight_line_distance_meters=0, data_updated_at=self.cutoff,
            )
            candidate = PlaceCandidate(decision_run_id=run.id, place_key=place.id, rank=1,
                                       place_snapshot=place.model_dump(mode="json"))
            session.add(candidate)
            await session.flush()
            return discovery.id, run.id, candidate.id

    async def test_expiry_boundaries_preserve_all_business_tables(self):
        await self.seed_temporary()
        discovery_id, run_id, candidate_id = await self.candidate()
        async with self.sessions.begin() as session:
            choice = PlaceChoice(user_id=self.user_id, discovery_session_id=discovery_id,
                                 place_candidate_id=candidate_id)
            task = Task(decision_run_id=run_id, status="running")
            session.add_all([choice, task, Preference(user_id=self.user_id)])
            await session.flush()
            session.add_all([
                PreferenceSample(user_id=self.user_id, discovery_session_id=discovery_id, choice_id=choice.id,
                                 meal_number=1, prefill_snapshot={}, active_changes={}, final_conditions={},
                                 request_text="", restaurant_facts={}),
                TaskStep(task_id=task.id, key="search", ordinal=0),
                TaskEvent(task_id=task.id, sequence=1, event_type="heartbeat", payload={}),
            ])
        before = await self.table_counts()
        counts = await self.sweep()
        self.assertEqual(counts, {name: 2 for name in (
            "place_cache", "auth_sessions", "idempotency_records", "auth_rate_limits",
        )})
        after = await self.table_counts()
        for name in before:
            self.assertEqual(after[name], 1 if name in counts else before[name], name)
        self.assertFalse(any((await self.sweep()).values()))

    async def test_dry_run_counts_without_writes_and_logs_no_private_content(self):
        await self.seed_temporary()
        before = await self.table_counts()
        with self.assertLogs("food.maintenance", level="INFO") as logs:
            counts = await self.sweep(dry_run=True)
        self.assertTrue(all(count == 2 for count in counts.values()))
        self.assertEqual(await self.table_counts(), before)
        self.assertTrue(all(json.loads(record.getMessage())["dryRun"] for record in logs.records))
        self.assertNotIn("private", "".join(logs.output))

    async def seed_sessions(self, count):
        async with self.sessions.begin() as session:
            await session.execute(insert(AuthSession), [{
                "user_id": self.user_id, "token_hash": f"bulk-{index}", "csrf_token": "private",
                "expires_at": self.cutoff - timedelta(seconds=1),
            } for index in range(count)])

    async def test_overlapping_cleanups_delete_multiple_batches_once(self):
        await self.seed_sessions(1003)
        with patch.object(maintenance, "now", return_value=self.cutoff):
            results = await asyncio.wait_for(asyncio.gather(
                maintenance.cleanup(self.sessions), maintenance.cleanup(self.sessions),
            ), timeout=10)
        self.assertEqual(sum(result["auth_sessions"] for result in results), 1003)
        self.assertEqual((await self.table_counts())["auth_sessions"], 0)

    async def test_failed_batch_rolls_back_without_undoing_committed_batches(self):
        await self.seed_sessions(1003)
        deletes = 0

        class FailingSession(AsyncSession):
            async def execute(self, statement, *args, **kwargs):
                nonlocal deletes
                result = await super().execute(statement, *args, **kwargs)
                if isinstance(statement, Delete) and statement.table.name == "auth_sessions":
                    deletes += 1
                    if deletes == 2:
                        raise RuntimeError("private failure text")
                return result

        sessions = async_sessionmaker(self.engine, class_=FailingSession)
        with self.assertLogs("food.maintenance", level="ERROR") as logs:
            with self.assertRaises(RuntimeError):
                await self.sweep(sessions=sessions)
        self.assertEqual((await self.table_counts())["auth_sessions"], 3)
        self.assertEqual(json.loads(logs.records[0].getMessage())["deleted"], 1000)
        self.assertNotIn("private failure text", "".join(logs.output))
        self.assertEqual((await self.sweep())["auth_sessions"], 3)

    async def test_locked_rate_limit_can_be_renewed_without_cleanup_deleting_it(self):
        async with self.sessions.begin() as session:
            row = AuthRateLimit(key_hash="rate-key", window_started_at=self.cutoff - timedelta(days=2), attempts=1)
            session.add(row)
            await session.flush()
            row_id = row.id
        async with self.sessions.begin() as busy:
            row = await busy.scalar(select(AuthRateLimit).where(AuthRateLimit.id == row_id).with_for_update())
            self.assertEqual((await asyncio.wait_for(self.sweep(), timeout=2))["auth_rate_limits"], 0)
            row.window_started_at = self.cutoff
        await SqlAuthRepository(self.sessions).consume_limit("rate-key", 10, 900)
        self.assertEqual((await self.sweep())["auth_rate_limits"], 0)
        async with self.sessions() as session:
            self.assertEqual((await session.get(AuthRateLimit, row_id)).attempts, 2)

    async def test_cache_write_recovers_when_cleanup_deletes_a_conflicting_row(self):
        cache = AmapCache(self.sessions, 600, 30)
        operation, params = "/v3/place/around", {"location": "121.47,31.23"}
        async with self.sessions.begin() as session:
            session.add(PlaceCache(cache_key=cache.key(operation, params), payload={},
                                   expires_at=self.cutoff - timedelta(seconds=1)))
        conflict, resume = asyncio.Event(), asyncio.Event()

        class PausingSession(AsyncSession):
            async def scalar(self, statement, *args, **kwargs):
                result = await super().scalar(statement, *args, **kwargs)
                if isinstance(statement, Insert) and result is None:
                    conflict.set()
                    await resume.wait()
                return result

        writer = AmapCache(async_sessionmaker(self.engine, class_=PausingSession), 600, 30)
        entry = FetchedResponse(payload={"status": "1", "pois": []}, fetched_at=self.cutoff)
        work = asyncio.create_task(writer.write(operation, params, entry, empty=False))
        try:
            await asyncio.wait_for(conflict.wait(), timeout=2)
            self.assertEqual((await asyncio.wait_for(self.sweep(), timeout=2))["place_cache"], 1)
        finally:
            resume.set()
            await asyncio.wait_for(work, timeout=5)
        self.assertEqual(await cache.read(operation, params), entry)

    async def test_cache_keeps_newer_data_and_replaces_damaged_payloads(self):
        cache = AmapCache(self.sessions, 600, 30)
        operation, params = "/v3/place/around", {"location": "121.47,31.23"}
        newest = FetchedResponse(payload={"value": "new"}, fetched_at=self.cutoff)
        older = FetchedResponse(payload={"value": "old"}, fetched_at=self.cutoff - timedelta(seconds=1))
        await cache.write(operation, params, newest, empty=False)
        await cache.write(operation, params, older, empty=False)
        self.assertEqual(await cache.read(operation, params), newest)
        async with self.sessions.begin() as session:
            await session.execute(update(PlaceCache).values(payload={"damaged": True}))
        await cache.write(operation, params, newest, empty=False)
        self.assertEqual(await cache.read(operation, params), newest)
        self.assertEqual((await self.sweep())["place_cache"], 0)

    async def expire_key(self, endpoint, key):
        async with self.sessions.begin() as session:
            await session.execute(update(IdempotencyRecord).where(
                IdempotencyRecord.user_id == self.user_id, IdempotencyRecord.endpoint == endpoint,
                IdempotencyRecord.idempotency_key == key,
            ).values(expires_at=self.cutoff))

    async def test_decision_idempotency_expires_with_or_without_scheduled_cleanup(self):
        async def complete(run_id):
            async with self.sessions.begin() as session:
                await session.execute(update(Task).where(Task.decision_run_id == run_id).values(
                    status="succeeded", completed_at=self.cutoff,
                ))
                await session.execute(update(DecisionRun).where(DecisionRun.id == run_id).values(
                    status="completed", completed_at=self.cutoff,
                ))

        service = DecisionCommandService(DecisionRepository(self.sessions, "test-model"), submissions_per_minute=10)
        request = DecisionCreateRequest(origin=Origin(latitude=31.23, longitude=121.47),
                                        prefill_snapshot=PrefillSnapshot(values=AccountPreferences(), source="defaults"))
        for cleaned in (False, True):
            with self.subTest(cleaned=cleaned):
                key = f"decision-{cleaned}"
                first = await service.create(self.user_id, request, key, str(uuid4()))
                self.assertEqual(await service.create(self.user_id, request, key, str(uuid4())), first)
                with self.assertRaises(AppError) as error:
                    await service.create(self.user_id, request.model_copy(update={"party_size": 2}), key, str(uuid4()))
                self.assertEqual(error.exception.code, "IDEMPOTENCY_CONFLICT")
                await self.expire_key("decision-runs", key)
                if cleaned:
                    await self.sweep()
                with self.assertRaises(AppError) as error:
                    await service.create(self.user_id, request, key, str(uuid4()))
                self.assertEqual(error.exception.code, "USER_TASK_LIMIT_REACHED")
                await complete(first)
                with patch("app.modules.decision.repository.transaction.now", return_value=self.cutoff):
                    second = await service.create(self.user_id, request, key, str(uuid4()))
                self.assertNotEqual(first, second)
                async with self.sessions() as session:
                    self.assertIsNotNone(await session.get(DecisionRun, first))
                    row = await session.scalar(select(IdempotencyRecord).where(IdempotencyRecord.idempotency_key == key))
                    self.assertEqual(row.expires_at, self.cutoff + timedelta(days=7))
                await complete(second)

    async def test_choice_idempotency_expires_with_or_without_scheduled_cleanup(self):
        service = ChoiceService(ChoiceRepository(self.sessions))
        for cleaned in (False, True):
            with self.subTest(cleaned=cleaned):
                key = f"choice-{cleaned}"
                _, first_run, first_candidate = await self.candidate()
                _, _, second_candidate = await self.candidate()
                first = await service.choose(self.user_id, first_candidate, key)
                selected = await DecisionRepository(self.sessions, "test-model").read_for_user(self.user_id, first_run)
                self.assertEqual((selected.choice.id, selected.choice.decision_run_id), (first["id"], first_run))
                self.assertEqual(await service.choose(self.user_id, first_candidate, key), first)
                with self.assertRaises(AppError) as error:
                    await service.choose(self.user_id, second_candidate, key)
                self.assertEqual(error.exception.code, "IDEMPOTENCY_CONFLICT")
                await self.expire_key("place-choices", key)
                if cleaned:
                    await self.sweep()
                with patch("app.modules.choice.transaction.now", return_value=self.cutoff):
                    second = await service.choose(self.user_id, second_candidate, key)
                self.assertNotEqual(first["id"], second["id"])
                async with self.sessions() as session:
                    self.assertIsNotNone(await session.get(PlaceChoice, first["id"]))

    async def test_cleanup_index_migration_upgrade_downgrade_and_metadata_match(self):
        async with self.engine.begin() as connection:
            await connection.run_sync(metadata.drop_all)

            def migrate(sync_connection):
                config = Config("alembic.ini")
                config.attributes["connection"] = sync_connection
                command.upgrade(config, "head")
                command.check(config)
                self.assertFalse(next(column for column in inspect(sync_connection).get_columns(
                    "discovery_sessions"
                ) if column["name"] == "prefill_snapshot")["nullable"])
                for table in ("auth_sessions", "idempotency_records", "auth_rate_limits"):
                    self.assertTrue(any(index["name"].endswith(("expires_at", "window_started_at"))
                                        for index in inspect(sync_connection).get_indexes(table)))
                command.downgrade(config, "0002")
                self.assertTrue(next(column for column in inspect(sync_connection).get_columns(
                    "discovery_sessions"
                ) if column["name"] == "prefill_snapshot")["nullable"])
                for table in ("auth_sessions", "idempotency_records", "auth_rate_limits"):
                    self.assertFalse(any(index["name"].endswith(("expires_at", "window_started_at"))
                                         for index in inspect(sync_connection).get_indexes(table)))
                command.upgrade(config, "head")

            await connection.run_sync(migrate)

    async def test_saved_choices_do_not_bypass_the_current_workflow_version(self):
        _, run_id, candidate_id = await self.candidate()
        await ChoiceService(ChoiceRepository(self.sessions)).choose(self.user_id, candidate_id, "choice")
        async with self.sessions.begin() as session:
            await session.execute(update(DecisionRun).where(DecisionRun.id == run_id).values(
                workflow_version=str(SCHEMA_VERSION - 1),
            ))
        repository = DecisionRepository(self.sessions, "test-model")
        for read in (repository.read_for_user, repository.stream_status):
            with self.subTest(read=read.__name__):
                with self.assertRaises(AppError) as caught:
                    await read(self.user_id, run_id)
                self.assertEqual((caught.exception.code, caught.exception.status), ("WORKFLOW_UPGRADED", 409))


if __name__ == "__main__":
    unittest.main()
