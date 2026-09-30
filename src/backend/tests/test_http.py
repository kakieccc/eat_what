from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from app import bootstrap
from app.api.errors.handlers import register_exception_handlers
from app.api.middleware import register_middlewares
from app.api.router import router
from app.modules.task.repository import TaskStore

pytestmark = pytest.mark.database


@pytest.fixture
async def api(sessions, settings, providers, monkeypatch):
    monkeypatch.setattr(bootstrap, "AmapGeoPlaceProvider", lambda *args: providers.amap)
    monkeypatch.setattr(bootstrap, "OpenAICompatibleFoodDecisionLlm", lambda *args: providers.llm)
    async with httpx.AsyncClient() as upstream:
        container = bootstrap.build_container(settings, sessions, upstream)
        app = FastAPI()
        app.state.settings = settings
        app.state.container = container
        app.state.ready = True
        register_exception_handlers(app)
        register_middlewares(app, settings)
        app.include_router(router)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://test"
        ) as client:
            yield SimpleNamespace(client=client, container=container)


async def register(client, username="httpuser"):
    response = await client.post(
        "/api/v2/auth/register",
        headers={"X-Auth-Intent": "web"},
        json={"username": username, "password": "test-password", "displayName": "测试用户"},
    )
    assert response.status_code == 201, response.text
    return response


async def test_auth_cookie_csrf_and_preferences(api):
    client = api.client
    response = await client.get("/api/v2/preferences")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"
    response = await register(client)
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
    assert response.headers["cache-control"] == "no-store"
    csrf = response.json()["data"]["csrfToken"]
    user = response.json()["data"]["user"]
    assert user["displayName"] == "测试用户"
    assert "createdAt" in user
    assert (await client.get("/api/v2/auth/me")).json()["data"]["user"] == user

    defaults = (await client.get("/api/v2/preferences")).json()["data"]
    assert defaults["maxWalkingMinutes"] == 15
    body = {**defaults, "preferredCuisines": ["面馆"], "maxWalkingMinutes": 20}
    assert (await client.put("/api/v2/preferences", json=body)).status_code == 403
    response = await client.put("/api/v2/preferences", json=body, headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200
    assert (await client.get("/api/v2/preferences")).json()["data"] == body
    invalid = {**body, "excludedCuisines": ["面馆"]}
    response = await client.put("/api/v2/preferences", json=invalid, headers={"X-CSRF-Token": csrf})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_INPUT"

    response = await client.post("/api/v2/auth/logout", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200
    assert (await client.get("/api/v2/auth/me")).status_code == 401
    response = await client.post(
        "/api/v2/auth/login",
        headers={"X-Auth-Intent": "web"},
        json={"username": "httpuser", "password": "test-password"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["user"]["id"] == user["id"]


async def test_decision_choice_history_and_sse_routes(api, sessions, decision_request):
    client = api.client
    signed_in = await register(client)
    headers = {
        "X-CSRF-Token": signed_in.json()["data"]["csrfToken"],
        "Idempotency-Key": "http-create",
    }
    response = await client.post(
        "/api/v2/decision-runs",
        json=decision_request.model_dump(mode="json", by_alias=True),
        headers=headers,
    )
    assert response.status_code == 201, response.text
    created = response.json()["data"]
    run_id = created["decisionRunId"]
    assert response.headers["location"] == f"/api/v2/decision-runs/{run_id}"
    store = TaskStore(sessions)
    claim = await store.claim(60)
    await api.container.worker.handler(claim)
    response = await client.get(f"/api/v2/decision-runs/{run_id}")
    result = response.json()["data"]
    assert result["status"] == "completed"
    candidate = result["places"][0]
    assert candidate["candidateId"] and candidate["rank"] == 1
    response = await client.get(f"/api/v2/decision-runs/{run_id}/events")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert "event: result" in response.text and "decisionRunId" in response.text
    headers["Idempotency-Key"] = "http-choice"
    response = await client.post(
        "/api/v2/place-choices",
        json={"candidateId": candidate["candidateId"], "feedback": "喜欢"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    history = await client.get("/api/v2/discovery-sessions")
    item = history.json()["data"]["items"][0]
    assert item["id"] == result["discoverySessionId"]
    assert item["choices"][0]["place"]["candidateId"] == candidate["candidateId"]
    runs = await client.get(f"/api/v2/discovery-sessions/{item['id']}/decision-runs")
    assert [run["decisionRunId"] for run in runs.json()["data"]] == [run_id]
    assert (await client.get("/api/v2/discovery-sessions?cursor=invalid")).status_code == 400

    await client.post("/api/v2/auth/logout", headers=headers)
    await register(client, "another_user")
    assert (await client.get(f"/api/v2/decision-runs/{run_id}")).status_code == 404
    assert (
        await client.get(f"/api/v2/discovery-sessions/{item['id']}/decision-runs")
    ).status_code == 404
    assert (await client.get("/api/v2/discovery-sessions")).json()["data"]["items"] == []


async def test_location_and_place_service_routes(api, providers):
    client = api.client
    await register(client)
    response = await client.get("/api/v2/resolved-locations?latitude=31.23&longitude=121.47")
    assert response.status_code == 200
    assert response.json()["data"]["address"] == "上海"
    response = await client.get("/api/v2/location-suggestions?query=上海")
    assert response.status_code == 200
    providers.amap.tips.assert_awaited_once_with("上海")
    response = await client.get("/api/v2/places?latitude=31.23&longitude=121.47")
    assert response.status_code == 200
    assert response.json()["data"][0]["externalId"] == "restaurant"
