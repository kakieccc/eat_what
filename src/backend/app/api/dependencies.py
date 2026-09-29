from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Header, Request

from app.application.auth.service import AuthContext
from app.application.container import Container
from app.core.errors import AppError


def container(request: Request) -> Container:
    if not getattr(request.app.state, "ready", False):
        raise AppError("DEPENDENCY_UNAVAILABLE", "数据库或工作流尚未就绪", 503, True)
    return cast(Container, request.app.state.container)


def idempotency_key(
    value: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=100)],
) -> str:
    return value


ContainerDependency = Annotated[Container, Depends(container)]
IdempotencyDependency = Annotated[str, Depends(idempotency_key)]


async def current_user(request: Request, services: ContainerDependency) -> AuthContext:
    return await services.auth.authenticate(request.cookies.get("food_session"))


async def mutation_user(
    services: ContainerDependency,
    user: Annotated[AuthContext, Depends(current_user)],
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> AuthContext:
    services.auth.verify_csrf(user, csrf_token)
    return user


CurrentUserDependency = Annotated[AuthContext, Depends(current_user)]
MutationUserDependency = Annotated[AuthContext, Depends(mutation_user)]
