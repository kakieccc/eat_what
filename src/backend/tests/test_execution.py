import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.core.clock import now
from app.modules.task.errors import LostTaskLease
from app.modules.task.models import Task
from app.modules.task.service import TaskWorker


@pytest.mark.database
async def test_empty_result_completes_without_relaxing_filters(
    system, providers, user_id, decision_request
):
    providers.amap.search.return_value = []
    run_id = await system.commands.create(user_id, decision_request, "empty-key", "request")
    claim = await system.tasks.claim(60)
    await system.runner.execute_claim(claim)
    result = await system.queries.get(run_id)
    assert result.status == "completed"
    assert result.places == []
    assert result.request == decision_request
    assert result.suggestions
    providers.amap.walking.assert_not_awaited()
    providers.llm.explain.assert_not_awaited()
    events = await system.tasks.events(claim.task_id)
    assert events[-1].payload["type"] == "result"


@pytest.mark.database
async def test_timeout_cancels_work_and_persists_failure(
    system, sessions, providers, user_id, decision_request
):
    cancelled = asyncio.Event()

    async def hang(*args):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    providers.amap.search.side_effect = hang
    system.runner.timeout_seconds = 0.1
    run_id = await system.commands.create(user_id, decision_request, "timeout-key", "request")
    claim = await system.tasks.claim(60)
    await asyncio.wait_for(system.runner.execute_claim(claim), 5)
    assert cancelled.is_set()
    result = await system.queries.get(run_id)
    assert result.status == "failed"
    assert result.error_code == "DECISION_TIMEOUT"
    async with sessions() as session:
        task = await session.get(Task, claim.task_id)
        assert task.status == "failed"
        assert task.lease_token is None
    events = await system.tasks.events(claim.task_id)
    assert events[-1].payload["type"] == "runFailed"


@pytest.mark.database
async def test_cancel_does_not_mark_run_failed(system, providers, user_id, decision_request):
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def hang(*args):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    providers.amap.search.side_effect = hang
    run_id = await system.commands.create(user_id, decision_request, "cancel-key", "request")
    claim = await system.tasks.claim(60)
    job = asyncio.create_task(system.runner.execute_claim(claim))
    try:
        await asyncio.wait_for(started.wait(), 5)
    finally:
        job.cancel()
        with pytest.raises(asyncio.CancelledError):
            await job
    assert cancelled.is_set()
    assert (await system.queries.get(run_id)).status == "running"
    assert all(
        event.payload["type"] != "runFailed" for event in await system.tasks.events(claim.task_id)
    )


@pytest.mark.database
async def test_reclaimed_task_rejects_old_lease(system, sessions, user_id, decision_request):
    run_id = await system.commands.create(user_id, decision_request, "lease-key", "request")
    old = await system.tasks.claim(60)
    async with sessions.begin() as session:
        task = await session.get(Task, old.task_id)
        task.lease_until = now() - timedelta(seconds=1)
    new = await system.tasks.claim(60)
    assert new.task_id == old.task_id
    assert new.lease_token != old.lease_token
    with pytest.raises(LostTaskLease):
        await system.tasks.renew(old, 60)
    with pytest.raises(LostTaskLease):
        await system.tasks.save_state(old, {"invalid": True}, "search_places")
    await system.runner.execute_claim(old)
    assert (await system.queries.get(run_id)).status == "pending"
    await system.runner.execute_claim(new)
    assert (await system.queries.get(run_id)).status == "completed"
    async with sessions() as session:
        task = await session.get(Task, new.task_id)
        assert "lease_token" not in task.state
        assert "invalid" not in task.state


@pytest.mark.database
async def test_refinement_rollback_keeps_parent(
    system, sessions, user_id, decision_request, monkeypatch
):
    from app.modules.decision.models import DecisionRun
    from app.modules.decision.repository.transaction import DecisionTransaction
    from app.modules.decision.schemas import SimpleRefinement

    run_id = await system.commands.create(user_id, decision_request, "create-key", "request")
    claim = await system.tasks.claim(60)
    await system.runner.execute_claim(claim)

    async def fail(*args, **kwargs):
        raise RuntimeError("injected enqueue failure")

    monkeypatch.setattr(DecisionTransaction, "enqueue", fail)
    with pytest.raises(RuntimeError, match="injected"):
        await system.commands.refine(
            user_id, run_id, SimpleRefinement(action="refresh"), "refine-key", "request"
        )
    async with sessions() as session:
        assert len(list(await session.scalars(select(DecisionRun)))) == 1
        assert len(list(await session.scalars(select(Task)))) == 1
    assert (await system.queries.get(run_id)).status == "completed"


async def test_worker_calls_handler_and_stops():
    claim = SimpleNamespace(task_id="task", lease_token="token")
    store = SimpleNamespace(claim=AsyncMock(return_value=claim))
    handler = AsyncMock()
    worker = TaskWorker(store, handler, poll_seconds=0.01)

    async def stop_after_execution(value):
        assert value is claim
        await worker.stop()

    handler.side_effect = stop_after_execution
    await asyncio.wait_for(worker.run(), 1)
    handler.assert_awaited_once_with(claim)
    store.claim.assert_awaited_once_with(60)
