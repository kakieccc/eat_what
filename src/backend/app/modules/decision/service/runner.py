from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import cast

from app.core.errors import AppError
from app.modules.decision.ports import DecisionRepository, FoodDecisionLlm
from app.modules.decision.workflow.context import execution_deadline
from app.modules.decision.workflow.events import (
    NodeCompleted,
    ProgressEvent,
    RunStarted,
)
from app.modules.decision.workflow.graph import build_graph
from app.modules.decision.workflow.state import SCHEMA_VERSION, State
from app.modules.places.service import PlaceService
from app.modules.task.ports import TaskStore
from app.modules.task.types import TaskClaim

log = logging.getLogger("food.decision")


class DecisionRunner:
    def __init__(
        self,
        repository: DecisionRepository,
        tasks: TaskStore,
        places: PlaceService,
        llm: FoodDecisionLlm,
        timeout_seconds: float,
    ) -> None:
        self.repository = repository
        self.tasks = tasks
        self.timeout_seconds = timeout_seconds
        self.graph = build_graph(places, llm, self.emit, self.step_started, self.step_completed)

    async def execute_claim(self, claim: TaskClaim) -> None:
        task_id, run_id, request_id, state, elapsed_ms = await self.repository.prepare(claim)
        if state.get("already_completed"):
            return
        if state.get("schema_version") != SCHEMA_VERSION:
            raise AppError("WORKFLOW_UPGRADED", "任务版本已更新，请重新推荐", 409)
        remaining = self.timeout_seconds - elapsed_ms / 1000
        if remaining <= 0:
            raise TimeoutError
        started = time.monotonic()
        deadline = asyncio.get_running_loop().time() + remaining
        token = execution_deadline.set(deadline)
        try:
            async with asyncio.timeout_at(deadline):
                await self.emit(claim, RunStarted(request_id=request_id, decision_run_id=run_id))
                result = cast(State, await self.graph.ainvoke(state))
        finally:
            execution_deadline.reset(token)
        duration = elapsed_ms + int((time.monotonic() - started) * 1000)
        await self.repository.complete(claim, result, run_id, duration)

    async def step_started(self, state: State, name: str) -> None:
        await self.tasks.start_step(
            TaskClaim(task_id=state["task_id"], lease_token=state["lease_token"]),
            name,
        )

    async def step_completed(self, state: State, name: str) -> None:
        await self.tasks.complete_step(
            TaskClaim(task_id=state["task_id"], lease_token=state["lease_token"]),
            name,
        )

    async def emit(self, claim: TaskClaim, event: ProgressEvent) -> None:
        await self.tasks.append_event(claim, event)
        if isinstance(event, NodeCompleted):
            log.info(
                json.dumps(
                    {
                        "event": "nodeCompleted",
                        "taskId": claim.task_id,
                        "graphNode": event.node,
                        "durationMs": event.duration_ms,
                        "placeCount": event.output_count,
                    }
                )
            )

    async def fail(self, claim: TaskClaim, error: Exception) -> None:
        is_timeout = isinstance(error, TimeoutError)
        failure = (
            error
            if isinstance(error, AppError)
            else AppError(
                "DECISION_TIMEOUT" if is_timeout else "INTERNAL_ERROR",
                "本次推荐超时，请重试或减少条件" if is_timeout else "执行失败，请重新推荐",
                504 if is_timeout else 500,
                is_timeout,
            )
        )
        await self.repository.fail(claim, failure.code, failure.message, failure.retryable)
        log.error("Task %s failed with %s", claim.task_id, failure.code, exc_info=error)
