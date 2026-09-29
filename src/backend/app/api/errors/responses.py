from __future__ import annotations

from typing import Any

from app.api.errors.models import ErrorEnvelope

DESCRIPTIONS = {
    400: "Invalid request",
    401: "Authentication required",
    403: "Forbidden",
    404: "Resource not found",
    409: "Resource state conflict",
    422: "Request validation failed",
    429: "Rate limited",
    500: "Internal server error",
    502: "Upstream service failed",
    503: "Dependency unavailable",
    504: "Operation timed out",
}


def error_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    return {
        status: {"model": ErrorEnvelope, "description": DESCRIPTIONS[status]}
        for status in statuses
    }
