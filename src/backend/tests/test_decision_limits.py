import asyncio
import multiprocessing
import unittest
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
from fastapi import FastAPI
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import container
from app.api.errors import register_exception_handlers
from app.api.middleware import register_middlewares
from app.core.clock import now
from app.core.config import Settings
from app.core.errors import AppError
from app.infrastructure.database.metadata import metadata
from app.modules.auth.dependencies import mutation_user
from app.modules.auth.models import User
from app.modules.decision.models import DecisionRun, DiscoverySession, IdempotencyRecord
from app.modules.decision.repository.repository import DecisionRepository
from app.modules.decision.router import router
from app.modules.decision.schemas import DecisionCreateRequest, SimpleRefinement
from app.modules.decision.service.commands import DecisionCommandService
from app.modules.location.schemas import Origin
from app.modules.preferences.schemas import AccountPreferences, PrefillSnapshot
from app.modules.task.models import Task
from app.modules.task.repository import TaskStore
from app.modules.task.service import TaskWorker


def decision_request():
    return DecisionCreateRequest(
        origin=Origin(latitude=31.23, longitude=121.47),
        prefill_snapshot=PrefillSnapshot(values=AccountPreferences(), source="defaults"),
    )


def submit_in_process(schema, user_id, key, start, results):
    async def submit():
        engine = create_async_engine(Settings().db_url, connect_args={
            "server_settings": {"search_path": schema},
        })
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        service = DecisionCommandService(DecisionRepository(sessions, "test-model"))
        try:
            run_id = await service.create(user_id, decision_request(), key, str(uuid4()))
            return ("accepted", run_id)
        except AppError as error:
            return (error.code, error.status)
        finally:
            await engine.dispose()

    start.wait(timeout=15)
    results.put(asyncio.run(submit()))


class DecisionLimitTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.schema = "test_decision_limits_" + uuid4().hex
        self.engine = create_async_engine(Settings().db_url, connect_args={
            "server_settings": {"search_path": self.schema},
        })
        self.addAsyncCleanup(self.cleanup_schema)
        async with self.engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))
            await connection.run_sync(metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.repository = DecisionRepository(self.sessions, "test-model")
        self.service = DecisionCommandService(self.repository)
        self.request = decision_request()
        async with self.sessions.begin() as session:
            users = [User(username=name, display_name=name, password="test-hash")
                     for name in ("alpha", "beta")]
            session.add_all(users)
            await session.flush()
            self.user_id, self.other_user_id = (user.id for user in users)

    async def cleanup_schema(self):
        try:
            async with self.engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE'))
        finally:
            await self.engine.dispose()

    async def create(self, key=None, user_id=None):
        return await self.service.create(
            user_id or self.user_id, self.request, key or str(uuid4()), str(uuid4()),
        )

    async def finish(self, run_id, status="succeeded"):
        async with self.sessions.begin() as session:
            await session.execute(update(Task).where(Task.decision_run_id == run_id).values(
                status=status, completed_at=now(), lease_token=None, lease_until=None,
            ))
            await session.execute(update(DecisionRun).where(DecisionRun.id == run_id).values(
                status="completed" if status == "succeeded" else "failed", completed_at=now(),
            ))

    async def counts(self):
        async with self.sessions() as session:
            return {model.__tablename__: await session.scalar(select(func.count()).select_from(model))
                    for model in (DiscoverySession, DecisionRun, Task, IdempotencyRecord)}

    async def create_users(self, count):
        async with self.sessions.begin() as session:
            users = [User(username=uuid4().hex, display_name="Test", password="test-hash")
                     for _ in range(count)]
            session.add_all(users)
            await session.flush()
            return [user.id for user in users]

    async def process_submissions(self, user_ids):
        context = multiprocessing.get_context("spawn")
        start, results = context.Barrier(len(user_ids)), context.Queue()
        processes = [context.Process(target=submit_in_process, args=(
            self.schema, user_id, f"process-{index}", start, results,
        )) for index, user_id in enumerate(user_ids)]
        try:
            for process in processes:
                process.start()
            await asyncio.gather(*(asyncio.to_thread(process.join, 25) for process in processes))
            self.assertEqual([process.exitcode for process in processes], [0] * len(processes))
            return [results.get(timeout=2) for _ in processes]
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
                    process.join(5)
            results.close()
            results.join_thread()

    async def test_distinct_keys_across_processes_share_one_task_slot(self):
        responses = await self.process_submissions([self.user_id] * 4)
        self.assertEqual(sum(code == "accepted" for code, _ in responses), 1, responses)
        self.assertEqual(sum(response == ("USER_TASK_LIMIT_REACHED", 429)
                             for response in responses), 3, responses)
        self.assertEqual(set((await self.counts()).values()), {1})

    async def test_global_limit_is_atomic_across_users_and_processes(self):
        responses = await self.process_submissions(await self.create_users(6))
        self.assertEqual(sum(code == "accepted" for code, _ in responses), 4, responses)
        self.assertEqual(sum(response == ("QUEUE_FULL", 503) for response in responses), 2, responses)
        self.assertEqual(set((await self.counts()).values()), {4})

    async def test_full_queue_preserves_replays_and_releases_capacity_at_terminal_state(self):
        users = await self.create_users(4)
        runs = [await self.create(f"global-{index}", user_id) for index, user_id in enumerate(users)]
        async with self.sessions.begin() as session:
            await session.execute(update(Task).where(Task.decision_run_id.in_(runs[:2])).values(status="running"))
        before = await self.counts()
        with self.assertRaises(AppError) as caught:
            await self.create()
        self.assertEqual((caught.exception.code, caught.exception.status, caught.exception.retry_after),
                         ("QUEUE_FULL", 503, 10))
        self.assertEqual(await self.create("global-0", users[0]), runs[0])
        self.assertEqual(await self.counts(), before)
        await self.finish(runs[0], "failed")
        await self.create()
        self.assertEqual((await self.counts())["tasks"], 5)

    async def test_queued_and_running_tasks_block_new_keys_but_allow_idempotent_replays(self):
        runs = await asyncio.gather(*(self.create("same-key") for _ in range(8)))
        self.assertEqual(len(set(runs)), 1)
        before = await self.counts()
        for status in ("queued", "running"):
            with self.subTest(status=status):
                async with self.sessions.begin() as session:
                    await session.execute(update(Task).values(status=status))
                with self.assertRaises(AppError) as caught:
                    await self.create()
                self.assertEqual((caught.exception.code, caught.exception.status, caught.exception.retryable),
                                 ("USER_TASK_LIMIT_REACHED", 429, True))
                self.assertEqual(await self.create("same-key"), runs[0])
                self.assertEqual(await self.counts(), before)
        with self.assertRaises(AppError) as caught:
            await self.service.create(self.user_id, self.request.model_copy(update={"party_size": 2}),
                                      "same-key", str(uuid4()))
        self.assertEqual(caught.exception.code, "IDEMPOTENCY_CONFLICT")

    async def test_terminal_tasks_release_the_slot(self):
        self.service = DecisionCommandService(self.repository, submissions_per_minute=10)
        for status in ("succeeded", "failed", "cancelled", "superseded"):
            with self.subTest(status=status):
                await self.finish(await self.create(), status)
        await self.create()
        async with self.sessions() as session:
            self.assertEqual(await session.scalar(select(func.count()).select_from(Task).where(
                Task.status.in_(("queued", "running")),
            )), 1)

    async def test_one_users_active_task_and_lock_do_not_block_another_user(self):
        await self.create()
        async with self.repository.transaction(self.user_id):
            await asyncio.wait_for(self.create(user_id=self.other_user_id), timeout=5)
        self.assertEqual((await self.counts())["tasks"], 2)

    async def test_retry_and_refinement_share_the_limit_and_preserve_replays(self):
        self.service = DecisionCommandService(self.repository, submissions_per_minute=10)
        failed = await self.create()
        await self.finish(failed, "failed")
        completed = await self.create()
        await self.finish(completed)
        active = await self.create()
        before = await self.counts()
        refinement = SimpleRefinement(action="refresh")
        for command in (
            lambda: self.service.retry(self.user_id, failed, "retry-key", str(uuid4())),
            lambda: self.service.refine(self.user_id, completed, refinement, "refine-key", str(uuid4())),
        ):
            with self.assertRaises(AppError) as caught:
                await command()
            self.assertEqual(caught.exception.code, "USER_TASK_LIMIT_REACHED")
            self.assertEqual(await self.counts(), before)
        self.assertEqual((await self.repository.read_for_user(self.user_id, failed)).status, "failed")
        self.assertEqual((await self.repository.read_for_user(self.user_id, completed)).status, "completed")
        await self.finish(active)
        retried = await self.service.retry(self.user_id, failed, "retry-key", str(uuid4()))
        self.assertEqual(await self.service.retry(self.user_id, failed, "retry-key", str(uuid4())), retried)
        await self.finish(retried)
        refined = await self.service.refine(self.user_id, completed, refinement, "refine-key", str(uuid4()))
        self.assertEqual(await self.service.refine(self.user_id, completed, refinement, "refine-key", str(uuid4())), refined)

    async def test_rolling_rate_window_counts_failed_tasks_and_excludes_replays_and_rejections(self):
        current = now()
        for index, (age, status) in enumerate(((59.2, "succeeded"), (30, "failed"), (5, "cancelled"))):
            run_id = await self.create(f"rate-{index}")
            await self.finish(run_id, status)
            async with self.sessions.begin() as session:
                await session.execute(update(Task).where(Task.decision_run_id == run_id).values(
                    created_at=current - timedelta(seconds=age),
                ))
        before = await self.counts()
        with patch("app.modules.decision.repository.transaction.now", return_value=current):
            with self.assertRaises(AppError) as caught:
                await self.create("rate-rejected")
            self.assertEqual((caught.exception.code, caught.exception.status, caught.exception.retry_after),
                             ("USER_TASK_RATE_LIMITED", 429, 1))
            self.assertEqual(await self.create("rate-2"), run_id)
        self.assertEqual(await self.counts(), before)
        with patch("app.modules.decision.repository.transaction.now", return_value=current + timedelta(microseconds=799999)):
            with self.assertRaises(AppError):
                await self.create("rate-rejected")
        with patch("app.modules.decision.repository.transaction.now", return_value=current + timedelta(milliseconds=800)):
            await self.create("rate-rejected")
        self.assertEqual((await self.counts())["tasks"], 4)

    async def test_creation_failure_rolls_back_admission_and_rate_usage(self):
        with patch("app.modules.decision.repository.transaction.DecisionTransaction.enqueue", side_effect=RuntimeError("enqueue failed")):
            with self.assertRaisesRegex(RuntimeError, "enqueue failed"):
                await self.create()
        self.assertEqual(set((await self.counts()).values()), {0})
        for _ in range(3):
            await self.finish(await asyncio.wait_for(self.create(), timeout=5))
        with self.assertRaises(AppError) as caught:
            await self.create()
        self.assertEqual(caught.exception.code, "USER_TASK_RATE_LIMITED")

    async def test_worker_bounds_claims_renews_each_lease_and_cleans_up_on_shutdown(self):
        for user_id in await self.create_users(4):
            await self.create(user_id=user_id)
        store = TaskStore(self.sessions)
        active, started, renewed = set(), [], set()
        release = {}
        two_started, third_started, heartbeats = asyncio.Event(), asyncio.Event(), asyncio.Event()
        maintaining, maintenance_stopped = asyncio.Event(), asyncio.Event()

        async def execute(claim):
            active.add(claim.task_id)
            started.append(claim.task_id)
            release[claim.task_id] = asyncio.Event()
            if len(started) == 2:
                two_started.set()
            if len(started) == 3:
                third_started.set()
            try:
                await release[claim.task_id].wait()
                async with self.sessions.begin() as session:
                    await session.execute(update(Task).where(Task.id == claim.task_id).values(status="succeeded"))
            finally:
                active.remove(claim.task_id)

        async def maintain():
            maintaining.set()
            try:
                await asyncio.Future()
            finally:
                maintenance_stopped.set()

        original_renew = store.renew

        async def renew(claim, lease_seconds):
            await original_renew(claim, lease_seconds)
            renewed.add(claim.task_id)
            if len(renewed) == 2:
                heartbeats.set()

        handler = SimpleNamespace(execute_claim=execute, fail=AsyncMock())
        worker = TaskWorker(store, handler, lease_seconds=3, poll_seconds=0.01, maintenance=maintain, concurrency=2)
        with patch.object(store, "renew", side_effect=renew), patch.object(worker, "_maintain", wraps=worker._maintain) as maintenance:
            running = asyncio.create_task(worker.run())
            try:
                await asyncio.wait_for(two_started.wait(), timeout=5)
                await asyncio.wait_for(maintaining.wait(), timeout=5)
                self.assertEqual(len(started), 2)
                self.assertEqual(maintenance.call_count, 1)
                async with self.sessions() as session:
                    statuses = list((await session.scalars(select(Task.status))).all())
                self.assertEqual(sorted(statuses), ["queued", "queued", "running", "running"])
                await asyncio.wait_for(heartbeats.wait(), timeout=5)
                self.assertEqual(renewed, set(started))
                release[started[0]].set()
                await asyncio.wait_for(third_started.wait(), timeout=5)
                self.assertEqual(len(active), 2)
                self.assertEqual(len(set(started)), 3)
            finally:
                running.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await running
        self.assertFalse(active)
        self.assertTrue(maintenance_stopped.is_set())
        handler.fail.assert_not_awaited()
        async with self.sessions() as session:
            statuses = list((await session.scalars(select(Task.status))).all())
        self.assertEqual(sorted(statuses), ["queued", "running", "running", "succeeded"])

    async def test_queue_expiry_releases_the_slot(self):
        first = await self.create()
        async with self.sessions.begin() as session:
            await session.execute(update(Task).values(created_at=now() - timedelta(seconds=61)))
        with self.assertRaises(AppError):
            await self.create()
        await TaskStore(self.sessions).expire_queued()
        self.assertEqual((await self.repository.read_for_user(self.user_id, first)).error_code, "QUEUE_TIMEOUT")
        self.assertNotEqual(await self.create(), first)

    def api(self):
        app = FastAPI()
        app.include_router(router)
        register_exception_handlers(app)
        register_middlewares(app, Settings(cors_origins="http://frontend.test"))
        services = SimpleNamespace(decision_commands=self.service,
                                   decision_queries=SimpleNamespace(get_for_user=self.repository.read_for_user))
        app.dependency_overrides[container] = lambda: services
        app.dependency_overrides[mutation_user] = lambda: SimpleNamespace(user=SimpleNamespace(id=self.user_id))
        return app

    async def test_api_returns_structured_429_and_documents_all_creation_routes(self):
        app = self.api()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            body = self.request.model_dump(mode="json", by_alias=True)
            accepted = await client.post("/decision-runs", json=body, headers={"Idempotency-Key": "accepted-key"})
            self.assertEqual(accepted.status_code, 201, accepted.text)
            before = await self.counts()
            rejected = await client.post("/decision-runs", json=body, headers={"Idempotency-Key": "rejected-key"})
            self.assertEqual(rejected.status_code, 429)
            self.assertEqual(rejected.json()["meta"]["requestId"], rejected.headers["X-Request-ID"])
            self.assertEqual(rejected.json()["error"], {
                "code": "USER_TASK_LIMIT_REACHED", "message": "已有推荐任务排队或执行中，请等待完成后再试",
                "details": {"retryable": True},
            })
            replay = await client.post("/decision-runs", json=body, headers={"Idempotency-Key": "accepted-key"})
            self.assertEqual(replay.status_code, 201)
            self.assertEqual(replay.json()["data"], accepted.json()["data"])
            self.assertEqual(await self.counts(), before)
        for path in ("/decision-runs", "/decision-runs/{run_id}/retry", "/decision-runs/{run_id}/refinements"):
            self.assertIn("429", app.openapi()["paths"][path]["post"]["responses"])

    async def test_api_full_queue_returns_retry_after_and_exposes_header_to_frontend(self):
        for user_id in await self.create_users(4):
            await self.create(user_id=user_id)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(self.api()), base_url="http://test") as client:
            response = await client.post("/decision-runs", json=self.request.model_dump(mode="json", by_alias=True),
                                         headers={"Idempotency-Key": "full-queue", "Origin": "http://frontend.test"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "QUEUE_FULL")
        self.assertEqual(response.headers["Retry-After"], "10")
        self.assertIn("Retry-After", response.headers["Access-Control-Expose-Headers"])
        self.assertEqual(set((await self.counts()).values()), {4})

    async def test_api_rate_limit_returns_retry_after_without_creating_a_task(self):
        for _ in range(3):
            await self.finish(await self.create())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(self.api()), base_url="http://test") as client:
            response = await client.post("/decision-runs", json=self.request.model_dump(mode="json", by_alias=True),
                                         headers={"Idempotency-Key": "rate-limited"})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["error"]["code"], "USER_TASK_RATE_LIMITED")
        self.assertTrue(1 <= int(response.headers["Retry-After"]) <= 60)
        self.assertEqual(set((await self.counts()).values()), {3})


if __name__ == "__main__":
    unittest.main()
