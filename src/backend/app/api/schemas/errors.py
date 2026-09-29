from __future__ import annotations

from pydantic import Field

from app.api.schemas.common import ApiModel


class ApiError(ApiModel):
    code: str
    message: str
    retryable: bool = False


class ErrorDetails(ApiModel):
    message: str = Field(default="")
