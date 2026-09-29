"""Compatibility exports for the decision stream schema."""

from __future__ import annotations

from app.workflows.food_decision.events import (
    ConfirmationRequired,
    DecisionEvent,
    Heartbeat,
    NodeCompleted,
    NodeStarted,
    Progress,
    ProviderStatus,
    ResultEvent,
    RunFailed,
    RunStarted,
    WarningEvent,
)

StreamEvent = DecisionEvent

__all__ = [
    "ConfirmationRequired",
    "DecisionEvent",
    "Heartbeat",
    "NodeCompleted",
    "NodeStarted",
    "Progress",
    "ProviderStatus",
    "ResultEvent",
    "RunFailed",
    "RunStarted",
    "StreamEvent",
    "WarningEvent",
]
