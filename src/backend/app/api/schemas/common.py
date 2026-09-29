from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=lambda value: "".join(
            part if index == 0 else part[:1].upper() + part[1:]
            for index, part in enumerate(value.split("_"))
        ),
        populate_by_name=True,
        extra="forbid",
    )


class Envelope[T](ApiModel):
    success: bool = True
    data: T
    meta: dict[str, JsonValue] = Field(default_factory=dict)


def dump_json(value: Any) -> Any:
    """Keep JSON conversion at the HTTP boundary."""

    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True)
    return value
