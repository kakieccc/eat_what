from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from app.modules.decision.workflow.events import ProgressEvent
from app.modules.decision.workflow.state import DecisionState
from app.modules.task.types import TaskClaim

Emitter = Callable[[TaskClaim, ProgressEvent], Awaitable[None]]
StepCallback = Callable[[DecisionState, str], Awaitable[None]]

# ContextVar isolates concurrent runs and keeps runtime deadlines out of persisted state.
execution_deadline: ContextVar[float | None] = ContextVar("decision_execution_deadline", default=None)
