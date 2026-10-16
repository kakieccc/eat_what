from __future__ import annotations

from typing import Any, TypedDict

SCHEMA_VERSION = 9
PROMPT_VERSION = "7"


class DecisionState(TypedDict, total=False):
    schema_version: int
    task_id: str
    lease_token: str
    decision_run_id: str
    request: dict[str, Any]
    places: list[dict[str, Any]]
    excluded: list[str]
    recent: list[str]
    old_cuisines: list[str]
    action: str
    intent: dict[str, Any]
    search_keywords: list[str]
    next_node: str
    filter_summary: dict[str, int]
    already_completed: bool


State = DecisionState
