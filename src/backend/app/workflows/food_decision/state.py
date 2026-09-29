from __future__ import annotations

from typing import Any, TypedDict


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
    changes: dict[str, Any]
    awaiting_confirmation: bool
    confirmation_answer: bool | None
    resume_from: str | None
    current_node: str
    filter_summary: dict[str, int]
    persisted: bool
    already_completed: bool


State = DecisionState
