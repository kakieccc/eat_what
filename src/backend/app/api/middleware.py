from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.api.errors.handlers import error_response
from app.core.config import Settings
from app.core.errors import AppError


# 处理跨域请求
def _allowed_origins(settings: Settings) -> list[str]:
    return [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]


def register_middlewares(app: FastAPI, settings: Settings) -> None:
    allowed = _allowed_origins(settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed,
        allow_methods=["GET", "POST", "PUT", "PATCH"],
        allow_headers=["Accept", "Content-Type", "Idempotency-Key", "X-Request-ID", "X-CSRF-Token", "X-Auth-Intent"],
        allow_credentials=True,
        expose_headers=["Location", "X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            request.state.request_id = str(UUID(request.headers.get("X-Request-ID", "")))
        except ValueError:
            request.state.request_id = str(uuid4())

        origin = request.headers.get("origin")
        response: Response
        if request.method in {"POST", "PUT", "PATCH"} and origin and origin not in allowed:
            response = error_response(
                request,
                AppError("INVALID_ORIGIN", "请求来源不允许", 403),
            )
        else:
            response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response
