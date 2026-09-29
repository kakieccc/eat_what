from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.workflows.food_decision.events import DecisionEvent
from app.workflows.food_decision.state import DecisionState

Emitter = Callable[[str, DecisionEvent], Awaitable[None]]
Persist = Callable[[DecisionState], Awaitable[None]]
StepStarted = Callable[[DecisionState, str], Awaitable[None]]
StateSaver = Callable[[DecisionState, str], Awaitable[None]]
