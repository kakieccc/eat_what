from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol

from app.application.decision.models import DecisionRunResponse
from app.application.task.models import TaskClaim
from app.domain.decision.models import DecisionRequest
from app.workflows.food_decision.state import State


@dataclass(frozen=True)
class IdempotencySnapshot:
    request_hash: str
    response_body: dict[str, object]


@dataclass(frozen=True)
class ParentSnapshot:
    status: str
    session_id: str
    request: DecisionRequest
    excluded_place_keys: list[str]
    previous_place_keys: list[str]
    place_snapshots: list[dict[str, object]]


@dataclass(frozen=True)
class ResumeSnapshot:
    status: str
    confirmation_pending: bool
    waiting_task_id: str | None
    waiting_state: State | None


class DecisionTransaction(Protocol):
    async def idempotency(self, endpoint: str, key: str) -> IdempotencySnapshot | None: ...
    async def record_idempotency(
        self, endpoint: str, key: str, digest: str, run_id: str, task_id: str
    ) -> None: ...
    async def parent(self, run_id: str) -> ParentSnapshot: ...
    async def create_discovery(self, request: DecisionRequest) -> str: ...
    async def create_run(
        self,
        session_id: str,
        request: DecisionRequest,
        parent_id: str | None,
        excluded: list[str],
        action: str,
    ) -> str: ...
    async def recent_place_keys(self) -> list[str]: ...
    async def enqueue(
        self,
        run_id: str,
        kind: str,
        request_id: str,
        state: State,
        parent_task_id: str | None = None,
    ) -> str: ...
    async def resume_snapshot(self, run_id: str) -> ResumeSnapshot: ...
    async def resolve_confirmation(self, run_id: str, accepted: bool | None) -> None: ...
    async def supersede(self, task_id: str) -> None: ...
    async def reset_run(self, run_id: str) -> None: ...


class DecisionRepository(Protocol):
    def transaction(self, user_id: str, lock_key: str) -> AbstractAsyncContextManager[DecisionTransaction]: ...
    async def read(self, run_id: str) -> DecisionRunResponse: ...
    async def read_for_user(self, user_id: str, run_id: str) -> DecisionRunResponse: ...
    async def prepare(self, claim: TaskClaim) -> tuple[str, str, str, State, int]: ...
    async def wait_for_confirmation(
        self, claim: TaskClaim, state: State, duration_ms: int
    ) -> None: ...
    async def complete(
        self, claim: TaskClaim, state: State, run_id: str, duration_ms: int
    ) -> None: ...
    async def fail(self, claim: TaskClaim, code: str, message: str) -> bool: ...
