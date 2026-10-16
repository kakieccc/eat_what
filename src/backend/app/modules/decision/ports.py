from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Protocol, TypeVar, cast

from app.core.models import Model
from app.modules.decision.schemas import DecisionIntent, DecisionRequest, DecisionRunResponse
from app.modules.decision.workflow.state import State
from app.modules.places.schemas import Place
from app.modules.task.types import TaskClaim


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
    retry_state: State = field(default_factory=lambda: cast(State, {}))


class DecisionTransaction(Protocol):
    async def idempotency(self, endpoint: str, key: str) -> IdempotencySnapshot | None: ...
    async def record_idempotency(
        self, endpoint: str, key: str, digest: str, run_id: str, task_id: str
    ) -> None: ...
    async def parent(self, run_id: str) -> ParentSnapshot: ...
    async def create_discovery(self, request: DecisionRequest) -> str: ...
    async def seen_place_keys(self, session_id: str) -> list[str]: ...
    async def set_intent(
        self, run_id: str, original: DecisionRequest, intent: DecisionIntent, duration_ms: int
    ) -> None: ...
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


class DecisionRepository(Protocol):
    def transaction(
        self, user_id: str, lock_key: str
    ) -> AbstractAsyncContextManager[DecisionTransaction]: ...
    async def read(self, run_id: str) -> DecisionRunResponse: ...
    async def read_for_user(self, user_id: str, run_id: str) -> DecisionRunResponse: ...
    async def prepare(self, claim: TaskClaim) -> tuple[str, str, str, State, int]: ...
    async def complete(
        self, claim: TaskClaim, state: State, run_id: str, duration_ms: int
    ) -> None: ...
    async def fail(self, claim: TaskClaim, code: str, message: str) -> bool: ...


T = TypeVar("T", bound=Model)


class StructuredLlm(Protocol):
    async def structured(self, schema: type[T], prompt: str, data: object) -> T: ...


class FoodDecisionLlm(Protocol):
    async def parse_intent(self, request: DecisionRequest) -> DecisionIntent: ...
    async def rerank(
        self,
        places: list[Place],
        preferences: DecisionRequest,
        intent: DecisionIntent,
        action: str = "",
        old_cuisines: list[str] | None = None,
    ) -> list[Place]: ...
    async def explain(self, places: list[Place]) -> list[Place]: ...
