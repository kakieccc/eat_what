from __future__ import annotations

from pydantic import Field, JsonValue

from app.core.models import Model


class Envelope[T](Model):
    success: bool = True
    data: T
    meta: dict[str, JsonValue] = Field(default_factory=dict)


class ErrorEnvelope(Model):
    success: bool = False
    error: dict[str, JsonValue]
    meta: dict[str, JsonValue] = Field(default_factory=dict)
