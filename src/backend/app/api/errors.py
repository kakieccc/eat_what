from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from app.api.schemas import ErrorEnvelope
from app.core.errors import AppError

log = logging.getLogger("food")


def error_response(request: Request, error: AppError) -> JSONResponse:
    body = ErrorEnvelope(
        error={
            "code": error.code,
            "message": error.message,
            "details": {"retryable": error.retryable},
        },
        meta={"requestId": getattr(request.state, "request_id", "")},
    )
    headers = {"Retry-After": str(error.retry_after)} if error.retry_after is not None else None
    return JSONResponse(
        body.model_dump(mode="json", by_alias=True), status_code=error.status, headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def application_error(request: Request, error: AppError) -> JSONResponse:
        return error_response(request, error)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _: RequestValidationError) -> JSONResponse:
        return error_response(
            request,
            AppError("INVALID_INPUT", "输入格式有误，请检查条件", 422),
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, error: SQLAlchemyError) -> JSONResponse:
        original = error.orig if isinstance(error, DBAPIError) else error
        log.error(json.dumps({
            "event": "databaseError",
            "exceptionType": type(error).__name__,
            "sqlstate": getattr(original, "sqlstate", None),
            "requestId": getattr(request.state, "request_id", ""),
        }))
        return error_response(
            request,
            AppError("DEPENDENCY_UNAVAILABLE", "数据库暂时不可用", 503, True),
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        messages = {404: "请求的资源不存在", 405: "请求方法不支持"}
        return error_response(
            request,
            AppError(
                f"HTTP_{error.status_code}",
                messages.get(error.status_code, str(error.detail)),
                error.status_code,
            ),
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception) -> JSONResponse:
        log.exception(
            json.dumps({
                "event": "unhandledError",
                "exceptionType": type(error).__name__,
                "requestId": getattr(request.state, "request_id", ""),
            }),
        )
        return error_response(
            request,
            AppError("INTERNAL_ERROR", "服务暂时无法完成请求", 500),
        )


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
        status: {"model": ErrorEnvelope, "description": DESCRIPTIONS[status]} for status in statuses
    }
