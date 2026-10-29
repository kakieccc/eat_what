import asyncio
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI

from app.api.dependencies import container, get_settings
from app.api.errors import register_exception_handlers
from app.core.clock import now
from app.core.errors import AppError
from app.infrastructure.amap.cache import AmapCache
from app.infrastructure.amap.provider import AmapGeoPlaceProvider
from app.infrastructure.amap.schemas import FetchedResponse
from app.modules.auth.dependencies import mutation_user
from app.modules.auth.passwords import Argon2PasswordHasher
from app.modules.auth.ports import UserRecord
from app.modules.auth.router import router as auth_router
from app.modules.auth.service import AuthContext, AuthService, profile
from app.modules.location.schemas import Point


class PasswordLimitTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.started = asyncio.Queue()
        self.gates = {name: threading.Event() for name in ("first", "second", "third", "cancelled", "error")}
        self.active = self.peak = 0
        loop = asyncio.get_running_loop()

        def work(password):
            self.active += 1
            self.peak = max(self.peak, self.active)
            loop.call_soon_threadsafe(self.started.put_nowait, password)
            try:
                if not self.gates[password].wait(5):
                    raise TimeoutError("test computation was not released")
                if password == "error":
                    raise RuntimeError("private password computation details")
                return password
            finally:
                self.active -= 1

        fake = SimpleNamespace(
            hash=lambda password: "dummy" if password == "not-a-real-account-password" else "hash-" + work(password),
            verify=lambda password, _: work(password) != "third",
        )
        with patch("app.modules.auth.passwords.PasswordHash.recommended", return_value=fake):
            self.hasher = Argon2PasswordHasher(wait_seconds=0.2)
        self.requests = []
        self.addAsyncCleanup(self.cleanup)

    def submit(self, operation):
        task = asyncio.create_task(operation)
        self.requests.append(task)
        return task

    async def cleanup(self):
        for gate in self.gates.values():
            gate.set()
        await self.hasher.aclose()
        await asyncio.gather(*self.requests, return_exceptions=True)

    async def next_computation(self):
        return await asyncio.wait_for(self.started.get(), timeout=2)

    async def test_running_cancellation_keeps_slot_and_waiting_cancellation_frees_queue(self):
        first = self.submit(self.hasher.hash("first"))
        self.assertEqual(await self.next_computation(), "first")
        cancelled = self.submit(self.hasher.hash("cancelled"))
        second = self.submit(self.hasher.hash("second"))
        await asyncio.sleep(0)
        with self.assertRaises(AppError) as caught:
            await self.hasher.hash("third")
        self.assertEqual((caught.exception.code, caught.exception.status, caught.exception.retry_after), ("AUTH_BUSY", 503, 1))
        cancelled.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await cancelled
        third = self.submit(self.hasher.verify("third", "hash"))
        await asyncio.sleep(0)
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        self.assertEqual(self.active, 1)
        with self.assertRaises(AppError):
            await self.hasher.hash("cancelled")
        self.gates["first"].set()
        self.assertEqual(await self.next_computation(), "second")
        self.gates["second"].set()
        self.assertEqual(await second, "hash-second")
        self.assertEqual(await self.next_computation(), "third")
        self.gates["third"].set()
        self.assertFalse(await third)
        self.assertEqual(self.peak, 1)
        self.assertTrue(self.started.empty())

    async def test_wait_timeout_and_shutdown_drain_the_actual_computation(self):
        first = self.submit(self.hasher.hash("first"))
        await self.next_computation()
        with self.assertRaises(AppError) as caught:
            await self.hasher.hash("second")
        self.assertEqual(caught.exception.code, "AUTH_BUSY")
        closing = self.submit(self.hasher.aclose())
        await asyncio.sleep(0)
        self.assertFalse(closing.done())
        with self.assertRaises(AppError):
            await self.hasher.verify("third", "hash")
        self.gates["first"].set()
        await first
        await closing
        self.assertFalse(self.hasher._running)
        self.assertEqual(self.active, 0)

    async def test_computation_error_releases_slot_without_logging_private_text(self):
        self.gates["error"].set()
        with self.assertLogs("food.auth", level="ERROR") as logs:
            with self.assertRaisesRegex(RuntimeError, "private password"):
                await self.hasher.hash("error")
        self.assertNotIn("private password", "".join(logs.output))
        self.gates["second"].set()
        self.assertEqual(await self.hasher.hash("second"), "hash-second")
        self.assertFalse(self.hasher._running)

    async def test_real_argon_password_and_dummy_verification_remain_valid(self):
        hasher = Argon2PasswordHasher()
        try:
            encoded = await hasher.hash("test-password")
            self.assertTrue(await hasher.verify("test-password", encoded))
            self.assertFalse(await hasher.verify("wrong-password", encoded))
            self.assertFalse(await hasher.verify("wrong-password", hasher.dummy_hash))
        finally:
            await hasher.aclose()

    async def test_busy_auth_endpoints_return_structured_503_without_writing_credentials(self):
        self.submit(self.hasher.hash("first"))
        await self.next_computation()
        self.submit(self.hasher.hash("second"))
        self.submit(self.hasher.hash("third"))
        await asyncio.sleep(0)
        user = UserRecord("user", "alpha", "Alpha", "encoded", now())
        repository = SimpleNamespace(consume_limit=AsyncMock(), by_username=AsyncMock(return_value=user),
                                     register=AsyncMock(), create_session=AsyncMock(), change_password=AsyncMock())
        auth = AuthService(repository, self.hasher, 30)
        app = FastAPI()
        app.include_router(auth_router)
        register_exception_handlers(app)
        app.dependency_overrides[container] = lambda: SimpleNamespace(auth=auth)
        app.dependency_overrides[get_settings] = lambda: SimpleNamespace(auth_session_days=30)
        app.dependency_overrides[mutation_user] = lambda: AuthContext(profile(user), "session", "csrf")
        requests = [
            ("/auth/login", {"username": "alpha", "password": "test-password"}),
            ("/auth/register", {"username": "alpha", "password": "test-password", "displayName": "Alpha"}),
            ("/auth/change-password", {"currentPassword": "test-password", "newPassword": "next-password"}),
        ]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            for path, body in requests:
                response = await client.post(path, json=body, headers={"X-Auth-Intent": "web"})
                self.assertEqual(response.status_code, 503, response.text)
                self.assertEqual(response.json()["error"]["code"], "AUTH_BUSY")
                self.assertEqual(response.headers["Retry-After"], "1")
                self.assertNotIn("Set-Cookie", response.headers)
        repository.register.assert_not_awaited()
        repository.create_session.assert_not_awaited()
        repository.change_password.assert_not_awaited()


class MapRequestMergeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.entries, self.requests = {}, []
        self.started = asyncio.Queue()
        self.release = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.error = None
        self.invalid_response = False

        async def read(operation, params):
            return self.entries.get(AmapCache.key(operation, params))

        async def write(operation, params, entry, *, empty):
            self.entries[AmapCache.key(operation, params)] = entry

        async def request(operation, params, *, deadline):
            self.started.put_nowait(params["id"])
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                self.cancelled.set()
                raise
            if self.error:
                raise self.error
            return self.response(params["id"], invalid=self.invalid_response)

        self.cache = SimpleNamespace(key=AmapCache.key, read=AsyncMock(side_effect=read), write=AsyncMock(side_effect=write))
        self.client = SimpleNamespace(request=AsyncMock(side_effect=request))
        self.provider = AmapGeoPlaceProvider(self.client, self.cache, 1)
        self.origin = Point(latitude=31.23, longitude=121.47)
        self.addAsyncCleanup(self.cleanup)

    @staticmethod
    def response(place_id="place", *, invalid=False):
        return FetchedResponse(payload={"status": "1", "pois": "invalid" if invalid else [
            {"id": place_id, "name": "Restaurant", "location": "121.47,31.23"},
        ]}, fetched_at=now())

    def detail(self, place_id="place", origin=None, deadline=None):
        task = asyncio.create_task(self.provider.detail(place_id, origin or self.origin, deadline=deadline))
        self.requests.append(task)
        return task

    async def cleanup(self):
        self.release.set()
        await asyncio.gather(*self.requests, return_exceptions=True)

    async def next_request(self):
        return await asyncio.wait_for(self.started.get(), timeout=1)

    async def test_same_key_shares_raw_response_and_maps_each_origin_independently(self):
        farther = Point(latitude=31.24, longitude=121.47)
        requests = [self.detail(origin=self.origin if index % 2 == 0 else farther) for index in range(10)]
        await self.next_request()
        self.assertEqual(self.client.request.await_count, 1)
        self.release.set()
        places = await asyncio.gather(*requests)
        self.assertLess(places[0].straight_line_distance_meters, places[1].straight_line_distance_meters)
        self.assertEqual(self.client.request.await_count, 1)
        self.cache.write.assert_awaited_once()
        self.assertFalse(self.provider._inflight)
        await self.provider.detail("place", self.origin)
        self.assertEqual(self.client.request.await_count, 1)

    async def test_different_keys_are_not_serialized(self):
        first, second = self.detail("one"), self.detail("two")
        self.assertEqual({await self.next_request(), await self.next_request()}, {"one", "two"})
        self.release.set()
        self.assertEqual({place.external_id for place in await asyncio.gather(first, second)}, {"one", "two"})

    async def test_first_waiter_cancellation_does_not_cancel_another_waiter(self):
        first = self.detail()
        await self.next_request()
        second = self.detail()
        await asyncio.sleep(0)
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        self.assertFalse(self.cancelled.is_set())
        self.release.set()
        self.assertEqual((await second).external_id, "place")
        self.assertEqual(self.client.request.await_count, 1)

    async def test_first_waiter_deadline_does_not_shorten_the_shared_request(self):
        first = self.detail(deadline=asyncio.get_running_loop().time() + 0.05)
        await self.next_request()
        second = self.detail()
        with self.assertRaises(AppError) as caught:
            await first
        self.assertEqual(caught.exception.code, "AMAP_UNAVAILABLE")
        self.assertFalse(second.done())
        self.assertFalse(self.cancelled.is_set())
        self.release.set()
        self.assertEqual((await second).external_id, "place")
        self.assertEqual(self.client.request.await_count, 1)

    async def test_last_waiter_cancels_the_shared_request_and_a_new_request_can_start(self):
        first, second = self.detail(), self.detail()
        await self.next_request()
        first.cancel()
        second.cancel()
        await asyncio.gather(first, second, return_exceptions=True)
        self.assertTrue(self.cancelled.is_set())
        self.assertFalse(self.provider._inflight)
        self.cache.write.assert_not_awaited()
        self.release.set()
        self.assertEqual((await self.detail()).external_id, "place")
        self.assertEqual(self.client.request.await_count, 2)

    async def test_failure_is_shared_and_a_later_request_can_retry(self):
        self.error = AppError("AMAP_UNAVAILABLE", "Unavailable", 502, True)
        first, second = self.detail(), self.detail()
        await self.next_request()
        self.release.set()
        errors = await asyncio.gather(first, second, return_exceptions=True)
        self.assertTrue(all(isinstance(error, AppError) and error.code == "AMAP_UNAVAILABLE" for error in errors))
        self.assertEqual(self.client.request.await_count, 1)
        self.cache.write.assert_not_awaited()
        self.assertFalse(self.provider._inflight)
        self.error = None
        self.assertEqual((await self.detail()).external_id, "place")

    async def test_invalid_cache_is_replaced_and_invalid_upstream_is_not_cached(self):
        key = AmapCache.key("/v3/place/detail", {"id": "place", "extensions": "all"})
        self.entries[key] = self.response(invalid=True)
        self.invalid_response = True
        self.release.set()
        with self.assertRaises(AppError) as caught:
            await self.detail()
        self.assertEqual(caught.exception.code, "AMAP_SCHEMA_ERROR")
        self.cache.write.assert_not_awaited()
        self.invalid_response = False
        self.assertEqual((await self.detail()).external_id, "place")
        self.assertIsInstance(self.entries[key].payload["pois"], list)

    async def test_rechecks_cache_after_becoming_the_shared_request_owner(self):
        entry = self.response()
        self.cache.read.side_effect = [None, entry]
        self.assertEqual((await self.detail()).external_id, "place")
        self.client.request.assert_not_awaited()
        self.cache.write.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
