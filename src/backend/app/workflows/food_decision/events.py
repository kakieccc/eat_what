from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue
from pydantic.alias_generators import to_camel


class WorkflowModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class WorkflowError(WorkflowModel):
    code: str
    message: str
    retryable: bool = False


class RunStarted(WorkflowModel):
    type: Literal["runStarted"] = "runStarted"
    request_id: str
    decision_run_id: str


class NodeStarted(WorkflowModel):
    type: Literal["nodeStarted"] = "nodeStarted"
    node: str
    label: str


class NodeCompleted(WorkflowModel):
    type: Literal["nodeCompleted"] = "nodeCompleted"
    node: str
    duration_ms: int
    output_count: int | None = None


class ResultEvent(WorkflowModel):
    type: Literal["result"] = "result"
    data: dict[str, JsonValue]


class ConfirmationRequired(WorkflowModel):
    type: Literal["confirmationRequired"] = "confirmationRequired"
    data: dict[str, JsonValue]


class RunFailed(WorkflowModel):
    type: Literal["runFailed"] = "runFailed"
    error: WorkflowError


class Heartbeat(WorkflowModel):
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
