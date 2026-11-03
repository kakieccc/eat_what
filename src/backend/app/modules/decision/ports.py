from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol, TypeVar

from app.core.models import Model
from app.modules.decision.schemas import DecisionRequest, DecisionRunResponse
from app.modules.decision.workflow.state import State
from app.modules.places.schemas import Place
from app.modules.preferences.schemas import PrefillSnapshot
from app.modules.task.types import TaskClaim


@dataclass(frozen=True)
class IdempotencySnapshot:
    request_hash: str
    response_body: dict[str, object]


@dataclass(frozen=True)
class RunStreamStatus:
    status: str
    error_code: str | None
    task_id: str | None


@dataclass(frozen=True)
class ParentSnapshot:
    status: str
    session_id: str
    request: DecisionRequest
    original_request: DecisionRequest
    has_choice: bool
    excluded_place_keys: list[str]
    places: list[Place]
    retry_state: State


class DecisionTransaction(Protocol):
    async def idempotency(self, endpoint: str, key: str) -> IdempotencySnapshot | None: ...
    async def require_task_capacity(self, max_active: int, submissions_per_minute: int) -> None: ...
    async def record_idempotency(
        self, endpoint: str, key: str, digest: str, run_id: str, task_id: str
    ) -> None: ...
    async def parent(self, run_id: str) -> ParentSnapshot: ...
    async def create_discovery(self, request: DecisionRequest, prefill: PrefillSnapshot) -> str: ...
    async def seen_place_keys(self, session_id: str) -> list[str]: ...
    async def create_run(
        self,
        session_id: str,
        request: DecisionRequest,
        parent_id: str | None,
        excluded: list[str],
        action: str,
        original: DecisionRequest,
    ) -> str: ...
    async def recent_place_keys(self) -> list[str]: ...
    async def enqueue(
        self,
        run_id: str,
        request_id: str,
        state: State,
    ) -> str: ...


class DecisionRepository(Protocol):
    def transaction(self, user_id: str) -> AbstractAsyncContextManager[DecisionTransaction]: ...
    async def read_for_user(self, user_id: str, run_id: str) -> DecisionRunResponse: ...
    async def stream_status(self, user_id: str, run_id: str) -> RunStreamStatus: ...
    async def prepare(self, claim: TaskClaim) -> tuple[str, str, str, State, int]: ...
    async def complete(
        self, claim: TaskClaim, state: State, run_id: str, duration_ms: int
    ) -> None: ...
    async def fail(self, claim: TaskClaim, code: str, message: str, retryable: bool) -> bool: ...


T = TypeVar("T", bound=Model)


class StructuredLlm(Protocol):
    async def structured(self, schema: type[T], prompt: str, data: object) -> T: ...


class FoodDecisionLlm(Protocol):
    async def filter_foods(self, places: list[Place], request: DecisionRequest) -> list[Place]: ...
    async def rerank(
        self,
        places: list[Place],
        request: DecisionRequest,
        action: str,
        old_cuisines: list[str],
    ) -> list[Place]: ...
