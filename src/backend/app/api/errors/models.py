from pydantic import Field, JsonValue

from app.api.schemas.common import ApiModel


class ErrorBody(ApiModel):
    code: str
    message: str
    details: dict[str, JsonValue] = Field(default_factory=dict)


class ErrorEnvelope(ApiModel):
    success: bool = False
    error: ErrorBody
    meta: dict[str, JsonValue] = Field(default_factory=dict)
