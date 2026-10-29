import asyncio
import json
import unittest
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI, Request
from pydantic import ValidationError
from sqlalchemy import delete, event, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import ClientDisconnect

from app.api.dependencies import container
from app.api.errors import register_exception_handlers
from app.core.clock import now
from app.core.config import Settings
from app.core.errors import AppError
from app.infrastructure.database.metadata import metadata
from app.modules.auth.dependencies import current_user
from app.modules.auth.models import AuthSession, User
from app.modules.auth.repository import SqlAuthRepository
from app.modules.auth.service import AuthService, digest
from app.modules.decision.models import DecisionRun, DiscoverySession
from app.modules.decision.ports import RunStreamStatus
from app.modules.decision.repository.repository import DecisionRepository
from app.modules.decision.router import router
from app.modules.decision.service.queries import DecisionQueryService
from app.modules.decision.service.streaming import DecisionStreamService
from app.modules.decision.workflow.events import Heartbeat
from app.modules.preferences.schemas import AccountPreferences, PrefillSnapshot
from app.modules.task.models import Task
from app.modules.task.repository import TaskStore


class StreamContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.queries = SimpleNamespace(
            stream_status=AsyncMock(return_value=RunStreamStatus("completed", None, "task")),
            get_for_user=AsyncMock(return_value=SimpleNamespace(
                model_dump=lambda **kwargs: {"authoritative": True},
            )),
        )
        self.auth = SimpleNamespace(authenticate=AsyncMock(
            return_value=SimpleNamespace(user=SimpleNamespace(id="user")),
        ))
        self.tasks = SimpleNamespace(events=AsyncMock(return_value=[SimpleNamespace(
            sequence=1, payload={"type": "nodeCompleted", "node": "search", "duration_ms": 1,
                                 "output_count": 0},
        )]))
        self.streams = DecisionStreamService(self.tasks, self.queries, self.auth)

    async def test_completed_stream_reads_its_result_from_business_tables(self):
        events = [event async for event in self.streams.stream("user", "run", "token")]
        self.assertEqual([event.type for event in events], ["nodeCompleted", "result"])
        self.assertEqual(events[-1].data, {"authoritative": True})
        self.queries.get_for_user.assert_awaited_once_with("user", "run")

    async def test_legacy_result_payloads_are_not_accepted_as_progress(self):
        self.tasks.events.return_value = [SimpleNamespace(
            sequence=1, payload={"type": "result", "data": {"legacy": True}},
        )]
        stream = self.streams.stream("user", "run", "token")
        with self.assertRaises(ValidationError):
            await anext(stream)
        self.queries.get_for_user.assert_not_awaited()


class StreamLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.queries = SimpleNamespace(stream_status=AsyncMock(return_value=RunStreamStatus("pending", None, "task")))
        self.auth = SimpleNamespace(authenticate=AsyncMock(return_value=SimpleNamespace(user=SimpleNamespace(id="alpha"))))
        self.tasks = SimpleNamespace(events=AsyncMock(return_value=[]))
        self.streams = DecisionStreamService(self.tasks, self.queries, self.auth)
        self.allow_body, self.finish = asyncio.Event(), asyncio.Event()
        self.streams.stream = self.body
        self.requests = []
        self.app = FastAPI()
        self.app.include_router(router)
        register_exception_handlers(self.app)
        self.app.dependency_overrides[container] = lambda: SimpleNamespace(
            decision_queries=self.queries, decision_streams=self.streams,
        )

        async def user(request: Request):
            return SimpleNamespace(user=SimpleNamespace(id=request.headers["x-test-user"]))

        self.app.dependency_overrides[current_user] = user
        self.run_id = str(uuid4())
        self.addAsyncCleanup(self.cleanup)

    async def body(self, user_id, run_id, token):
        await self.allow_body.wait()
        yield Heartbeat(timestamp=now())
        await self.finish.wait()

    async def open(self, user="alpha", *, run_id=None, spec="2.0", fail_send=False):
        incoming = asyncio.Queue()
        incoming.put_nowait({"type": "http.request", "body": b"", "more_body": False})
        request = SimpleNamespace(incoming=incoming, messages=[], started=asyncio.Event(),
                                  first_body=asyncio.Event(), status=None)

        async def send(message):
            request.messages.append(message)
            if message["type"] == "http.response.start":
                request.status = message["status"]
                request.started.set()
            if message["type"] == "http.response.body" and message.get("body"):
                request.first_body.set()
                if fail_send:
                    raise OSError("client disconnected")

        scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": spec},
                 "http_version": "1.1", "method": "GET", "scheme": "http",
                 "path": f"/decision-runs/{run_id or self.run_id}/events", "query_string": b"",
                 "root_path": "", "server": ("test", 80), "client": ("127.0.0.1", 1234),
                 "headers": [(b"x-test-user", user.encode()), (b"cookie", b"food_session=token")]}
        request.task = asyncio.create_task(self.app(scope, incoming.get, send))
        self.requests.append(request)
        await asyncio.wait_for(request.started.wait(), timeout=2)
        return request

    async def disconnect(self, request):
        request.incoming.put_nowait({"type": "http.disconnect"})
        await asyncio.wait_for(request.task, timeout=2)

    async def cleanup(self):
        for request in self.requests:
            if not request.task.done():
                request.task.cancel()
        await asyncio.gather(*(request.task for request in self.requests), return_exceptions=True)

    @staticmethod
    def data(request):
        return b"".join(message.get("body", b"") for message in request.messages)

    async def test_user_limit_is_checked_before_headers_and_first_frame_disconnect_releases_slot(self):
        first, second = await self.open(), await self.open()
        self.assertEqual((first.status, second.status), (200, 200))
        rejected = await self.open()
        await rejected.task
        self.assertEqual(rejected.status, 429)
        self.assertEqual(json.loads(self.data(rejected))["error"]["code"], "USER_STREAM_LIMIT_REACHED")
        self.assertEqual(dict(rejected.messages[0]["headers"])[b"retry-after"], b"2")
        self.assertEqual(self.queries.stream_status.await_count, 2)
        self.assertFalse(first.first_body.is_set())
        await self.disconnect(first)
        replacement = await self.open()
        self.assertEqual(replacement.status, 200)
        replacement.task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await replacement.task
        await self.disconnect(second)
        self.assertEqual(self.streams._connection_count, 0)
        self.assertFalse(self.streams._connections)

    async def test_global_limit_is_shared_by_all_users_and_cleanup_removes_user_counters(self):
        accepted = [await self.open(f"user-{index // 2}") for index in range(8)]
        rejected = await self.open("another-user")
        await rejected.task
        self.assertEqual(rejected.status, 503)
        self.assertEqual(json.loads(self.data(rejected))["error"]["code"], "STREAM_CAPACITY_REACHED")
        self.assertEqual(self.streams._connection_count, 8)
        self.assertEqual(self.queries.stream_status.await_count, 8)
        for request in accepted:
            await self.disconnect(request)
        self.assertEqual(self.streams._connection_count, 0)
        self.assertFalse(self.streams._connections)

    async def test_invalid_run_and_permission_failure_do_not_leak_slots(self):
        invalid = await self.open(run_id="invalid")
        await invalid.task
        self.assertEqual(invalid.status, 422)
        self.assertEqual(self.streams._connection_count, 0)
        self.queries.stream_status.side_effect = AppError("NOT_FOUND", "Not found", 404)
        missing = await self.open()
        await missing.task
        self.assertEqual(missing.status, 404)
        self.assertFalse(self.streams._connections)

    async def test_normal_stream_end_and_send_failure_release_slots(self):
        self.allow_body.set()
        self.finish.set()
        complete = await self.open()
        await complete.task
        self.assertIn(b"heartbeat", self.data(complete))
        self.assertEqual(self.streams._connection_count, 0)
        with self.assertLogs("food", level="ERROR"):
            failed = await self.open(spec="2.4", fail_send=True)
            with self.assertRaises(ClientDisconnect):
                await failed.task
        self.assertEqual(self.streams._connection_count, 0)
        self.assertFalse(self.streams._connections)

    async def test_revoked_session_ends_stream_and_releases_slot(self):
        del self.streams.stream
        request = await self.open()
        await asyncio.wait_for(request.first_body.wait(), timeout=2)
        self.auth.authenticate.side_effect = AppError("AUTH_REQUIRED", "Session revoked", 401)
        await asyncio.wait_for(request.task, timeout=2)
        self.assertIn(b"AUTH_REQUIRED", self.data(request))
        self.assertFalse(self.streams._connections)


class StreamQueryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.schema = "test_stream_queries_" + uuid4().hex
        self.engine = create_async_engine(Settings().db_url, connect_args={
            "server_settings": {"search_path": self.schema},
        })
        self.addAsyncCleanup(self.cleanup_schema)
        async with self.engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))
            await connection.run_sync(metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.sessions.begin() as session:
            user = User(username="stream-test", display_name="Before", password="test-hash")
            session.add(user)
            await session.flush()
            self.user_id = user.id
            session.add(AuthSession(user_id=user.id, token_hash=digest("token"), csrf_token="csrf",
                                    expires_at=now() + timedelta(hours=1)))
            discovery = DiscoverySession(
                user_id=user.id, request_snapshot={},
                prefill_snapshot=PrefillSnapshot(values=AccountPreferences(), source="defaults").model_dump(mode="json"),
            )
            session.add(discovery)
            await session.flush()
            run = DecisionRun(discovery_session_id=discovery.id)
            session.add(run)
            await session.flush()
            discovery.current_run_id = run.id
            session.add(Task(decision_run_id=run.id))
            self.run_id = run.id
        self.auth = AuthService(SqlAuthRepository(self.sessions), SimpleNamespace(), 30)
        self.queries = []

        def count_queries(connection, cursor, statement, parameters, context, executemany):
            self.queries.append(statement)

        event.listen(self.engine.sync_engine, "before_cursor_execute", count_queries)
        self.addCleanup(event.remove, self.engine.sync_engine, "before_cursor_execute", count_queries)

    async def cleanup_schema(self):
        try:
            async with self.engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE'))
        finally:
            await self.engine.dispose()

    async def test_authentication_uses_one_join_and_still_reads_changes_and_revocation(self):
        self.assertEqual((await self.auth.authenticate("token")).user.display_name, "Before")
        self.assertEqual(len(self.queries), 1)
        async with self.sessions.begin() as session:
            await session.execute(update(User).where(User.id == self.user_id).values(display_name="After"))
        self.queries.clear()
        self.assertEqual((await self.auth.authenticate("token")).user.display_name, "After")
        self.assertEqual(len(self.queries), 1)
        async with self.sessions.begin() as session:
            await session.execute(delete(AuthSession))
        self.queries.clear()
        with self.assertRaises(AppError) as caught:
            await self.auth.authenticate("token")
        self.assertEqual(caught.exception.code, "AUTH_REQUIRED")
        self.assertEqual(len(self.queries), 1)

    async def test_registration_only_labels_username_conflicts_as_username_taken(self):
        repository = SqlAuthRepository(self.sessions)
        expires = now() + timedelta(hours=1)
        await repository.register("beta", "Beta", "test-hash", "unique-token", "csrf", expires)
        with self.assertRaises(AppError) as caught:
            await repository.register("beta", "Beta", "test-hash", "another-token", "csrf", expires)
        self.assertEqual((caught.exception.code, caught.exception.status), ("USERNAME_TAKEN", 409))
        with self.assertRaises(IntegrityError):
            await repository.register("gamma", "Gamma", "test-hash", "unique-token", "csrf", expires)
        async with self.sessions() as session:
            self.assertIsNone(await session.scalar(select(User).where(User.username == "gamma")))

    async def test_waiting_stream_iteration_executes_three_queries(self):
        repository = DecisionRepository(self.sessions, "test-model")
        service = DecisionStreamService(TaskStore(self.sessions), DecisionQueryService(repository, None), self.auth)
        stream = service.stream(self.user_id, self.run_id, "token")
        try:
            self.assertEqual((await anext(stream)).type, "heartbeat")
            self.assertEqual(len(self.queries), 3)
        finally:
            await stream.aclose()


if __name__ == "__main__":
    unittest.main()
