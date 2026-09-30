from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.container import Container
from app.core.config import Settings
from app.infrastructure.amap.provider import AmapGeoPlaceProvider
from app.infrastructure.auth.passwords import Argon2PasswordHasher
from app.infrastructure.llm.provider import OpenAICompatibleFoodDecisionLlm
from app.infrastructure.persistence.session import create_sessions, engine_of
from app.modules.auth.repository import SqlAuthRepository
from app.modules.auth.service import AuthService
from app.modules.choice.repository import ChoiceRepository
from app.modules.choice.service import ChoiceService
from app.modules.decision.repository.repository import DecisionRepository
from app.modules.decision.service.commands import DecisionCommandService
from app.modules.decision.service.queries import DecisionQueryService
from app.modules.decision.service.runner import DecisionRunner
from app.modules.decision.service.streaming import DecisionStreamService
from app.modules.history.repository import HistoryRepository
from app.modules.history.service import HistoryService
from app.modules.location.service import LocationService
from app.modules.places.repository import PlacesRepository
from app.modules.places.service import PlaceService
from app.modules.preferences.repository import PreferencesRepository
from app.modules.preferences.service import PreferencesService
from app.modules.task.repository import TaskStore
from app.modules.task.service import TaskWorker


def build_container(
    settings: Settings,
    sessions: async_sessionmaker[AsyncSession],
    client: httpx.AsyncClient,
) -> Container:
    amap = AmapGeoPlaceProvider(client, sessions, settings)
    llm = OpenAICompatibleFoodDecisionLlm(settings)
    repository = DecisionRepository(sessions, settings.llm_model)
    auth = AuthService(
        SqlAuthRepository(sessions), Argon2PasswordHasher(), settings.auth_session_days
    )
    tasks = TaskStore(sessions)
    queries = DecisionQueryService(repository)
    runner = DecisionRunner(
        repository,
        tasks,
        queries,
        amap,
        llm,
        settings.task_lease_seconds,
        settings.decision_timeout_seconds,
    )
    worker = TaskWorker(
        tasks,
        runner.execute_claim,
        lease_seconds=settings.task_lease_seconds,
        poll_seconds=settings.task_poll_seconds,
    )
    return Container(
        auth=auth,
        settings=settings,
        sessions=sessions,
        amap=amap,
        llm=llm,
        worker=worker,
        decision_commands=DecisionCommandService(repository),
        decision_queries=queries,
        decision_streams=DecisionStreamService(tasks, queries, auth),
        location=LocationService(amap),
        places=PlaceService(PlacesRepository(sessions), amap),
        preferences=PreferencesService(PreferencesRepository(sessions)),
        history=HistoryService(HistoryRepository(sessions), queries),
        choices=ChoiceService(ChoiceRepository(sessions)),
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:

    settings = app.state.settings
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for name in ["httpx", "httpcore", "openai"]:
        logging.getLogger(name).setLevel(logging.WARNING)

    sessions = create_sessions(settings)
    app.state.ready = False
    app.state.settings = settings
    app.state.sessions = sessions
    async with httpx.AsyncClient(follow_redirects=False) as client:
        try:
            async with sessions() as db:
                await db.execute(text("SELECT 1"))
            app.state.container = build_container(settings, sessions, client)
            app.state.ready = True
            worker = asyncio.create_task(app.state.container.worker.run())
            try:
                yield
            finally:
                await app.state.container.worker.stop()
                worker.cancel()
                await asyncio.gather(worker, return_exceptions=True)
        finally:
            app.state.ready = False
            await engine_of(sessions).dispose()
