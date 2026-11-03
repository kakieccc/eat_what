from __future__ import annotations

from typing import TypedDict

from pydantic import TypeAdapter

from app.modules.decision.schemas import DecisionRequest
from app.modules.places.schemas import Place

SCHEMA_VERSION = 12
PROMPT_VERSION = "10"


class DecisionState(TypedDict, total=False):
    schema_version: int
    task_id: str
    lease_token: str
    decision_run_id: str
    request: DecisionRequest
    places: list[Place]
    excluded: list[str]
    recent: list[str]
    old_cuisines: list[str]
    action: str
    search_queue: list[tuple[str, int]]
    search_seen_ids: list[str]
    search_fallback_used: bool
    filter_summary: dict[str, int]
    already_completed: bool


State = DecisionState
STATE_ADAPTER = TypeAdapter(State)
