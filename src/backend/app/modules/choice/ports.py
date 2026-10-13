from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class IdempotencySnapshot:
    request_hash: str
    response_body: dict[str, object]


@dataclass(frozen=True)
class CandidateSnapshot:
    id: str
    discovery_session_id: str
    run_status: str


class ChoiceTransaction(Protocol):
    async def idempotency(self, key: str) -> IdempotencySnapshot | None: ...
    async def candidate(self, candidate_id: str) -> CandidateSnapshot: ...
    async def create_choice(
        self, candidate: CandidateSnapshot, feedback: str
    ) -> str: ...
    async def record_idempotency(
        self, key: str, digest: str, result: dict[str, str]
    ) -> None: ...


class ChoiceRepository(Protocol):
    def transaction(
        self, user_id: str, key: str
    ) -> AbstractAsyncContextManager[ChoiceTransaction]: ...
