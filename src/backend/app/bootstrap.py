from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.auth.service import AuthService
from app.application.choice.service import ChoiceService
from app.application.decision.commands import DecisionCommandService
from app.application.decision.queries import DecisionQueryService
from app.application.decision.runner import DecisionRunner
from app.application.decision.streaming import DecisionStreamService
from app.application.history.service import HistoryService
from app.application.location.service import LocationService
from app.application.places.service import PlaceService
from app.application.preferences.service import PreferencesService
from app.core.config import Settings
from app.infrastructure.amap.provider import AmapGeoPlaceProvider
from app.infrastructure.auth.passwords import Argon2PasswordHasher
from app.infrastructure.llm.provider import OpenAICompatibleFoodDecisionLlm
from app.infrastructure.persistence.repositories.auth import SqlAuthRepository
from app.infrastructure.persistence.repositories.choice import ChoiceRepository
from app.infrastructure.persistence.repositories.decision import DecisionRepository
from app.infrastructure.persistence.repositories.history import HistoryRepository
from app.infrastructure.persistence.repositories.places import PlacesRepository
from app.infrastructure.persistence.repositories.preferences import PreferencesRepository
from app.infrastructure.persistence.session import create_sessions, engine_of
from app.infrastructure.persistence.task_store import TaskStore, TaskWorker


@dataclass
class Container:
    auth: AuthService
    settings: Settings
    sessions: async_sessionmaker[AsyncSession]
    amap: AmapGeoPlaceProvider
    llm: OpenAICompatibleFoodDecisionLlm
    worker: TaskWorker
    decision_commands: DecisionCommandService
    decision_queries: DecisionQueryService
    decision_streams: DecisionStreamService
    location: LocationService
    places: PlaceService
    preferences: PreferencesService
    history: HistoryService
    choices: ChoiceService


def build_container(
    settings: Settings,
    sessions: async_sessionmaker[AsyncSession],
    client: httpx.AsyncClient,
) -> Container:
    amap = AmapGeoPlaceProvider(client, sessions, settings)
    llm = OpenAICompatibleFoodDecisionLlm(settings)
    repository = DecisionRepository(sessions, settings.llm_model)
    auth = AuthService(SqlAuthRepository(sessions), Argon2PasswordHasher())
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
        history=HistoryService(HistoryRepository(sessions)),
        choices=ChoiceService(ChoiceRepository(sessions)),
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:

    settings = Settings()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for name in ["httpx", "httpcore", "openai"]:
        logging.getLogger(name).setLevel(logging.WARNING)

    sessions = create_sessions(settings)
    app.state.ready = False
    app.state.settings = settings
    app.state.sessions = sessions
    async with httpx.AsyncClient(follow_redirects=False) as client:
        while not app.state.ready:
            try:
                async with sessions() as db:
                    await db.execute(text("SELECT 1"))
                app.state.container = build_container(settings, sessions, client)
                app.state.ready = True
            except Exception:
                logging.getLogger("food").warning(
                    '{"event":"dependencyNotReady","errorCode":"DEPENDENCY_UNAVAILABLE"}'
                )
                await asyncio.sleep(5)

        worker = asyncio.create_task(app.state.container.worker.run())
        try:
            yield
        finally:
            await app.state.container.worker.stop()
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
            app.state.ready = False

    await engine_of(sessions).dispose()
