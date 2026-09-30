import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.errors import AppError
from app.modules.choice.models import PlaceChoice
from app.modules.choice.repository import ChoiceRepository
from app.modules.choice.service import ChoiceService
from app.modules.choice.transaction import ChoiceTransaction
from app.modules.decision.models import DecisionRun, DiscoverySession, IdempotencyRecord
from app.modules.decision.repository.transaction import DecisionTransaction
from app.modules.decision.schemas import SimpleRefinement
from app.modules.task.models import Task

pytestmark = pytest.mark.database


async def completed_run(system, user_id, decision_request, key="create-key"):
    run_id = await system.commands.create(user_id, decision_request, key, "request")
    claim = await system.tasks.claim(60)
    assert claim is not None
    await system.runner.execute_claim(claim)
    result = await system.queries.get_for_user(user_id, run_id)
    assert result.status == "completed"
    return result


async def count(sessions, model):
    async with sessions() as session:
        return await session.scalar(select(func.count()).select_from(model))


async def test_create_concurrent_replay_and_conflict(system, sessions, user_id, decision_request):
    ids = await asyncio.gather(
        *(
            system.commands.create(user_id, decision_request, "same-key", "request")
            for _ in range(6)
        )
    )
    assert len(set(ids)) == 1
    for model in [DiscoverySession, DecisionRun, Task, IdempotencyRecord]:
        assert await count(sessions, model) == 1
    changed = decision_request.model_copy(update={"radius_meters": 3000})
    with pytest.raises(AppError, match="IDEMPOTENCY_CONFLICT"):
        await system.commands.create(user_id, changed, "same-key", "request")
    with pytest.raises(AppError, match="NOT_FOUND"):
        await system.queries.get_for_user(str(uuid4()), ids[0])


async def test_create_rolls_back_all_writes(
    system, sessions, user_id, decision_request, monkeypatch
):
    async def fail(*args, **kwargs):
        raise RuntimeError("injected persistence failure")

    monkeypatch.setattr(DecisionTransaction, "record_idempotency", fail)
    with pytest.raises(RuntimeError, match="injected"):
        await system.commands.create(user_id, decision_request, "rollback-key", "request")
    for model in [DiscoverySession, DecisionRun, Task, IdempotencyRecord]:
        assert await count(sessions, model) == 0


async def test_refine_concurrent_replay(system, sessions, user_id, decision_request):
    parent = await completed_run(system, user_id, decision_request)
    action = SimpleRefinement(action="refresh")
    ids = await asyncio.gather(
        *(
            system.commands.refine(user_id, parent.decision_run_id, action, "refine-key", "request")
            for _ in range(4)
        )
    )
    assert len(set(ids)) == 1
    assert await count(sessions, DiscoverySession) == 1
    assert await count(sessions, DecisionRun) == 2
    assert await count(sessions, Task) == 2
    async with sessions() as session:
        child = await session.get(DecisionRun, ids[0])
        assert child.parent_decision_id == parent.decision_run_id
        assert child.excluded_place_keys == [parent.places[0].id]
        task = await session.scalar(select(Task).where(Task.decision_run_id == child.id))
        assert task.state["schema_version"] == 4
        assert task.state["next_node"] == "search_places"
    with pytest.raises(AppError, match="IDEMPOTENCY_CONFLICT"):
        await system.commands.refine(
            user_id,
            parent.decision_run_id,
            SimpleRefinement(action="cheaper"),
            "refine-key",
            "request",
        )


async def test_refine_pending_run_rejected(system, user_id, decision_request):
    run_id = await system.commands.create(user_id, decision_request, "pending-key", "request")
    with pytest.raises(AppError, match="INVALID_STATE"):
        await system.commands.refine(
            user_id, run_id, SimpleRefinement(action="refresh"), "refine-key", "request"
        )


async def test_choice_concurrent_replay_and_conflict(system, sessions, user_id, decision_request):
    run = await completed_run(system, user_id, decision_request)
    candidate_id = run.places[0].candidate_id
    service = ChoiceService(ChoiceRepository(sessions))
    results = await asyncio.gather(
        *(service.choose(user_id, candidate_id, "喜欢", "choice-key") for _ in range(6))
    )
    assert all(result == results[0] for result in results)
    assert results[0]["candidateId"] == candidate_id
    assert await count(sessions, PlaceChoice) == 1
    with pytest.raises(AppError, match="IDEMPOTENCY_CONFLICT"):
        await service.choose(user_id, candidate_id, "不同反馈", "choice-key")
    async with sessions.begin() as session:
        row = await session.get(DecisionRun, run.decision_run_id)
        row.status = "pending"
    # A replay returns the original result before checking the current run status.
    assert await service.choose(user_id, candidate_id, "喜欢", "choice-key") == results[0]
    with pytest.raises(AppError, match="INVALID_STATE"):
        await service.choose(user_id, candidate_id, "", "new-choice-key")
    with pytest.raises(AppError, match="NOT_FOUND"):
        await service.choose(str(uuid4()), candidate_id, "", "other-user-key")
    with pytest.raises(AppError, match="NOT_FOUND"):
        await service.choose(user_id, str(uuid4()), "", "missing-key")


async def test_choice_rolls_back_insert(system, sessions, user_id, decision_request, monkeypatch):
    run = await completed_run(system, user_id, decision_request)
    original_records = await count(sessions, IdempotencyRecord)

    async def fail(*args, **kwargs):
        raise RuntimeError("injected persistence failure")

    monkeypatch.setattr(ChoiceTransaction, "record_idempotency", fail)
    with pytest.raises(RuntimeError, match="injected"):
        await ChoiceService(ChoiceRepository(sessions)).choose(
            user_id, run.places[0].candidate_id, "", "rollback-key"
        )
    assert await count(sessions, PlaceChoice) == 0
    assert await count(sessions, IdempotencyRecord) == original_records


@pytest.mark.parametrize("accept", [True, False])
async def test_confirmation_resume_is_atomic_and_replayable(
    system, sessions, providers, user_id, decision_request, accept
):
    from app.modules.decision.schemas import Intent

    providers.llm.parse_intent.return_value = Intent(max_walking_minutes=25)
    request = decision_request.model_copy(update={"request_text": "可以走远一点"})
    run_id = await system.commands.create(user_id, request, "confirm-create", "request")
    claim = await system.tasks.claim(60)
    await system.runner.execute_claim(claim)
    assert (await system.queries.get(run_id)).status == "awaitingConfirmation"
    with pytest.raises(AppError, match="CONFIRMATION_REQUIRED"):
        await system.commands.resume(user_id, run_id, None, "missing-answer", "request")
    ids = await asyncio.gather(
        *(
            system.commands.resume(user_id, run_id, accept, "resume-key", "request")
            for _ in range(4)
        )
    )
    assert len(set(ids)) == 1
    assert await count(sessions, Task) == 2
    with pytest.raises(AppError, match="IDEMPOTENCY_CONFLICT"):
        await system.commands.resume(user_id, run_id, not accept, "resume-key", "request")
    async with sessions() as session:
        task = await session.get(Task, ids[0])
        assert task.state["next_node"] == "confirm_intent"
        assert task.state["schema_version"] == 4
        assert "lease_token" not in task.state
    resumed = await system.tasks.claim(60)
    await system.runner.execute_claim(resumed)
    result = await system.queries.get(run_id)
    assert result.status == "completed"
    assert result.request.max_walking_minutes == (25 if accept else 15)
    providers.llm.parse_intent.assert_awaited_once()


async def test_resume_rollback_preserves_waiting_task(
    system, sessions, providers, user_id, decision_request, monkeypatch
):
    from app.modules.decision.models import DecisionConfirmation
    from app.modules.decision.schemas import Intent

    providers.llm.parse_intent.return_value = Intent(max_walking_minutes=25)
    request = decision_request.model_copy(update={"request_text": "走远一点"})
    run_id = await system.commands.create(user_id, request, "create-key", "request")
    claim = await system.tasks.claim(60)
    await system.runner.execute_claim(claim)

    async def fail(*args, **kwargs):
        raise RuntimeError("injected persistence failure")

    monkeypatch.setattr(DecisionTransaction, "record_idempotency", fail)
    with pytest.raises(RuntimeError, match="injected"):
        await system.commands.resume(user_id, run_id, True, "resume-key", "request")
    assert await count(sessions, Task) == 1
    async with sessions() as session:
        task = await session.get(Task, claim.task_id)
        confirmation = await session.scalar(select(DecisionConfirmation))
        assert task.status == "waiting_confirmation"
        assert confirmation.status == "pending"
    assert (await system.queries.get(run_id)).status == "awaitingConfirmation"
