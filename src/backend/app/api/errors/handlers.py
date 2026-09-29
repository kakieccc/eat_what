from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from app.api.errors.models import ErrorBody, ErrorEnvelope
from app.core.errors import AppError

log = logging.getLogger("food")


def error_response(
    request: Request,
    error: AppError,
    *,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    body = ErrorEnvelope(
        error=ErrorBody(
            code=error.code,
            message=error.message,
            details={"retryable": error.retryable, **(details or {})},
        ),
        meta={"requestId": getattr(request.state, "request_id", "")},
    )
    return JSONResponse(body.model_dump(mode="json", by_alias=True), status_code=error.status)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def application_error(request: Request, error: AppError) -> JSONResponse:
        return error_response(request, error)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        fields = [{"location": list(item["loc"]), "type": item["type"]} for item in error.errors()]
        return error_response(
            request,
            AppError("INVALID_INPUT", "输入格式有误，请检查条件", 422),
            details={"fields": fields},
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, _: SQLAlchemyError) -> JSONResponse:
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
            '{"event":"unhandledError","exceptionType":"%s"}',
            type(error).__name__,
        )
        return error_response(
            request,
            AppError("INTERNAL_ERROR", "服务暂时无法完成请求", 500),
        )
