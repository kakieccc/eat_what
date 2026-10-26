from dataclasses import dataclass


@dataclass(frozen=True)
class TaskClaim:
    task_id: str
    lease_token: str


@dataclass(frozen=True)
class EventRecord:
    sequence: int
    payload: dict[str, object]
