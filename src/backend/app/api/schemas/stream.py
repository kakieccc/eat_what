"""Compatibility exports for the decision stream schema."""

from __future__ import annotations

from app.workflows.food_decision.events import (
    ConfirmationRequired,
    DecisionEvent,
    Heartbeat,
    NodeCompleted,
    NodeStarted,
    ResultEvent,
    RunFailed,
    RunStarted,
)

StreamEvent = DecisionEvent

__all__ = [
    "ConfirmationRequired",
    "DecisionEvent",
    "Heartbeat",
    "NodeCompleted",
    "NodeStarted",
    "ResultEvent",
    "RunFailed",
    "RunStarted",
    "StreamEvent",
]
