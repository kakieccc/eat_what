from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import cast

from app.core.errors import AppError
from app.modules.decision.ports import DecisionRepository, FoodDecisionLlm
from app.modules.decision.schemas import DecisionRequest
from app.modules.decision.service.queries import DecisionQueryService
from app.modules.decision.workflow.context import execution_deadline
from app.modules.decision.workflow.events import (
    DecisionEvent,
    NodeCompleted,
    ResultEvent,
    RunFailed,
    RunStarted,
    WorkflowError,
)
from app.modules.decision.workflow.graph import build_graph
from app.modules.decision.workflow.state import SCHEMA_VERSION, State
from app.modules.places.service import PlaceService
from app.modules.task.errors import LostTaskLease
from app.modules.task.ports import TaskStore
from app.modules.task.types import TaskClaim

log = logging.getLogger("food.decision")


class DecisionRunner:
    def __init__(
        self,
        repository: DecisionRepository,
        tasks: TaskStore,
        queries: DecisionQueryService,
        places: PlaceService,
        llm: FoodDecisionLlm,
        lease_seconds: int,
        timeout_seconds: float,
    ) -> None:
        self.repository = repository
        self.tasks = tasks
        self.queries = queries
        self.lease_seconds = lease_seconds
        self.timeout_seconds = timeout_seconds
        self.graph = build_graph(places, llm, self.emit, self.step_started, self.save_state)

    async def execute_claim(self, claim: TaskClaim) -> None:
        graph_job = asyncio.create_task(self._execute_task(claim))
        pulse = asyncio.create_task(self._heartbeat(claim))
        try:
            done, _ = await asyncio.wait({graph_job, pulse}, return_when=asyncio.FIRST_COMPLETED)
            if pulse in done:
                await pulse
            await graph_job
        except LostTaskLease:
            graph_job.cancel()
            await asyncio.gather(graph_job, return_exceptions=True)
            log.info("Task lease lost: %s", claim.task_id)
        except asyncio.CancelledError:
            graph_job.cancel()
            await asyncio.gather(graph_job, return_exceptions=True)
            raise
        except Exception as error:
            await self._fail_task(claim, error)
        finally:
            graph_job.cancel()
            pulse.cancel()
            await asyncio.gather(graph_job, pulse, return_exceptions=True)

    async def _heartbeat(self, claim: TaskClaim) -> None:
        while True:
            await asyncio.sleep(max(1, min(10, self.lease_seconds / 3)))
            await self.tasks.renew(claim, self.lease_seconds)

    async def _execute_task(self, claim: TaskClaim) -> None:
        started = time.monotonic()
        task_id, run_id, request_id, state, elapsed_ms = await self.repository.prepare(claim)
        if state.get("already_completed"):
            return
        if state.get("schema_version") != SCHEMA_VERSION:
            raise AppError("WORKFLOW_UPGRADED", "任务版本已更新，请重新推荐", 409)
        DecisionRequest.model_validate(state["request"])
        await self.emit(task_id, RunStarted(request_id=request_id, decision_run_id=run_id))
        remaining = self.timeout_seconds - elapsed_ms / 1000
        deadline = asyncio.get_running_loop().time() + max(0.001, remaining)
        token = execution_deadline.set(deadline)
        try:
            async with asyncio.timeout_at(deadline):
                result = cast(State, await self.graph.ainvoke(state))
        finally:
            execution_deadline.reset(token)
        duration = int((time.monotonic() - started) * 1000)
        await self.repository.complete(claim, result, run_id, duration)
        await self.emit(task_id, ResultEvent(data=await self.queries.response_json(run_id)))

    async def step_started(self, state: State, name: str) -> None:
        await self.tasks.start_step(
            TaskClaim(task_id=str(state["task_id"]), lease_token=str(state["lease_token"])),
            name,
        )

    async def save_state(self, state: State, phase: str) -> None:
        await self.tasks.save_state(
            TaskClaim(task_id=str(state["task_id"]), lease_token=str(state["lease_token"])),
            dict(state),
            phase,
        )

    async def emit(self, task_id: str, event: DecisionEvent) -> None:
        await self.tasks.append_event(task_id, event)
        if isinstance(event, NodeCompleted):
            log.info(
                json.dumps(
                    {
                        "event": "nodeCompleted",
                        "taskId": task_id,
                        "graphNode": event.node,
                        "durationMs": event.duration_ms,
                        "placeCount": event.output_count,
                    }
                )
            )

    async def _fail_task(self, claim: TaskClaim, error: Exception) -> None:
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
        updated = await self.repository.fail(claim, failure.code, failure.message)
        if updated:
            await self.emit(
                claim.task_id,
                RunFailed(
                    error=WorkflowError(
                        code=failure.code,
                        message=failure.message,
                        retryable=failure.retryable,
                    )
                ),
            )
        log.error("Task %s failed with %s", claim.task_id, failure.code, exc_info=error)
