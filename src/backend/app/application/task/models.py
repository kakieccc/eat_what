from dataclasses import dataclass


class LostTaskLease(RuntimeError):
    """Raised when a worker no longer owns a task."""


@dataclass(frozen=True)
class TaskClaim:
    task_id: str
    lease_token: str


@dataclass(frozen=True)
class TaskSnapshot:
    id: str
    status: str


@dataclass(frozen=True)
class EventRecord:
    sequence: int
    payload: dict[str, object]
