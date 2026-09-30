from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, JsonValue

from app.core.models import Model


class WorkflowError(Model):
    code: str
    message: str
    retryable: bool = False


class RunStarted(Model):
    type: Literal["runStarted"] = "runStarted"
    request_id: str
    decision_run_id: str


class NodeStarted(Model):
    type: Literal["nodeStarted"] = "nodeStarted"
    node: str
    label: str


class NodeCompleted(Model):
    type: Literal["nodeCompleted"] = "nodeCompleted"
    node: str
    duration_ms: int
    output_count: int | None = None


class ResultEvent(Model):
    type: Literal["result"] = "result"
    data: dict[str, JsonValue]


class ConfirmationRequired(Model):
    type: Literal["confirmationRequired"] = "confirmationRequired"
    data: dict[str, JsonValue]


class RunFailed(Model):
    type: Literal["runFailed"] = "runFailed"
    error: WorkflowError


class Heartbeat(Model):
    type: Literal["heartbeat"] = "heartbeat"
    timestamp: datetime


DecisionEvent = Annotated[
    RunStarted
    | NodeStarted
    | NodeCompleted
    | ResultEvent
    | ConfirmationRequired
    | RunFailed
    | Heartbeat,
    Field(discriminator="type"),
]
