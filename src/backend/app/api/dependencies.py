from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.container import Container
from app.core.config import Settings
from app.core.errors import AppError


def container(request: Request) -> Container:
    if not getattr(request.app.state, "ready", False):
        raise AppError("DEPENDENCY_UNAVAILABLE", "数据库或工作流尚未就绪", 503, True)
    return cast(Container, request.app.state.container)


def idempotency_key(
    value: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=100)],
) -> str:
    return value

def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_sessions(services: ContainerDependency) -> async_sessionmaker[AsyncSession]:
    return services.sessions

ContainerDependency = Annotated[Container, Depends(container)]
IdempotencyDependency = Annotated[str, Depends(idempotency_key)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
SessionsDependency = Annotated[async_sessionmaker[AsyncSession], Depends(get_sessions)]