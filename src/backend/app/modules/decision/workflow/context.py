from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.modules.decision.workflow.events import DecisionEvent
from app.modules.decision.workflow.state import DecisionState

Emitter = Callable[[str, DecisionEvent], Awaitable[None]]
StepStarted = Callable[[DecisionState, str], Awaitable[None]]
StateSaver = Callable[[DecisionState, str], Awaitable[None]]
