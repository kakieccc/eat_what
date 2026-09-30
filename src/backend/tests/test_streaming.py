from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.errors import AppError
from app.modules.decision.schemas import DecisionRunResponse
from app.modules.decision.service import streaming
from app.modules.decision.service.streaming import DecisionStreamService
from app.modules.task.types import EventRecord, TaskSnapshot


def services(events, task_status="running"):
    auth = SimpleNamespace(
        authenticate=AsyncMock(return_value=SimpleNamespace(user=SimpleNamespace(id="user")))
    )
    tasks = SimpleNamespace(
        latest_for_run=AsyncMock(return_value=TaskSnapshot("task", task_status)),
        events=AsyncMock(return_value=events),
    )
    queries = SimpleNamespace(get_for_user=AsyncMock())
    return DecisionStreamService(tasks, queries, auth), tasks, queries, auth


@pytest.mark.parametrize("terminal", ["result", "confirmationRequired", "runFailed"])
async def test_replay_stops_at_terminal_event(terminal):
    payload = {"type": terminal, "data": {}}
    if terminal == "runFailed":
        payload = {"type": terminal, "error": {"code": "FAILED", "message": "失败"}}
    events = [
        EventRecord(1, {"type": "runStarted", "request_id": "request", "decision_run_id": "run"}),
        EventRecord(2, payload),
        EventRecord(3, {"type": "result", "data": {}}),
    ]
    service, tasks, queries, auth = services(events)
    received = [event async for event in service.stream("user", "run", "request", "token")]
    assert [event.type for event in received] == ["runStarted", terminal]
    tasks.events.assert_awaited_once_with("task", 0)
    queries.get_for_user.assert_not_awaited()
    auth.authenticate.assert_awaited_once_with("token")
    assert received[0].model_dump(by_alias=True)["decisionRunId"] == "run"


@pytest.mark.parametrize(
    "status,terminal",
    [
        ("completed", "result"),
        ("awaitingConfirmation", "confirmationRequired"),
        ("failed", "runFailed"),
    ],
)
async def test_terminal_result_fallback(decision_request, status, terminal):
    service, tasks, queries, auth = services([], "succeeded")
    queries.get_for_user.return_value = DecisionRunResponse(
        decision_run_id="run",
        discovery_session_id="session",
        status=status,
        request=decision_request,
    )
    received = [event async for event in service.stream("user", "run", "request", "token")]
    assert [event.type for event in received] == [terminal]
    queries.get_for_user.assert_awaited_once_with("user", "run")


async def test_heartbeat_and_session_revalidation(monkeypatch):
    service, tasks, queries, auth = services([])
    auth.authenticate.side_effect = [
        SimpleNamespace(user=SimpleNamespace(id="user")),
        AppError("AUTH_REQUIRED", "会话失效", 401),
    ]
    ticks = iter([0, 16, 16])
    monkeypatch.setattr(streaming, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
    monkeypatch.setattr(streaming, "asyncio", SimpleNamespace(sleep=AsyncMock()))
    stream = service.stream("user", "run", "request", "token")
    assert (await anext(stream)).type == "heartbeat"
    with pytest.raises(AppError, match="AUTH_REQUIRED"):
        await anext(stream)
    assert auth.authenticate.await_count == 2


async def test_changed_user_cannot_receive_events():
    service, tasks, queries, auth = services([])
    auth.authenticate.return_value = SimpleNamespace(user=SimpleNamespace(id="other"))
    assert [event async for event in service.stream("user", "run", "request", "token")] == []
    tasks.events.assert_not_awaited()
