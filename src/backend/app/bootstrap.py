from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.container import Container
from app.core.config import Settings
from app.infrastructure.amap.cache import AmapCache
from app.infrastructure.amap.client import AmapClient
from app.infrastructure.amap.provider import AmapGeoPlaceProvider
from app.infrastructure.database.session import create_sessions, engine_of
from app.infrastructure.llm.provider import OpenAICompatibleLlm
from app.modules.auth.passwords import Argon2PasswordHasher
from app.modules.auth.repository import SqlAuthRepository
from app.modules.auth.service import AuthService
from app.modules.choice.repository import ChoiceRepository
from app.modules.choice.service import ChoiceService
from app.modules.decision.repository.repository import DecisionRepository
from app.modules.decision.service.commands import DecisionCommandService
from app.modules.decision.service.llm import DecisionLlmService
from app.modules.decision.service.queries import DecisionQueryService
from app.modules.decision.service.runner import DecisionRunner
from app.modules.decision.service.streaming import DecisionStreamService
from app.modules.history.repository import HistoryRepository
from app.modules.history.service import HistoryService
from app.modules.places.repository import PlacesRepository
from app.modules.places.service import PlaceService
from app.modules.preferences.learning import PreferenceLearner
from app.modules.preferences.repository import PreferencesRepository
from app.modules.task.repository import TaskStore
from app.modules.task.service import TaskWorker


def build_container(
    settings: Settings,
    sessions: async_sessionmaker[AsyncSession],
    client: httpx.AsyncClient,
    llm_client: AsyncOpenAI,
) -> Container:
    amap = AmapGeoPlaceProvider(
        AmapClient(client, settings),
        AmapCache(
            sessions,
            settings.amap_cache_ttl_seconds,
            settings.amap_empty_cache_ttl_seconds,
        ),
        settings.amap_operation_timeout_seconds,
    )
    places = PlaceService(PlacesRepository(sessions), amap, settings.amap_operation_timeout_seconds)
    structured_llm = OpenAICompatibleLlm(settings, llm_client)
    llm = DecisionLlmService(structured_llm)
    preferences = PreferencesRepository(sessions)
    learner = PreferenceLearner(preferences, structured_llm, settings.task_lease_seconds)
    preference_worker = TaskWorker(
        preferences, learner.execute_claim, lease_seconds=settings.task_lease_seconds,
        poll_seconds=settings.task_poll_seconds,
    )
    repository = DecisionRepository(sessions, settings.llm_model)
    auth = AuthService(
        SqlAuthRepository(sessions), Argon2PasswordHasher(), settings.auth_session_days
    )
    tasks = TaskStore(sessions, settings.task_queue_timeout_seconds)
    queries = DecisionQueryService(repository, places)
    runner = DecisionRunner(
        repository,
        tasks,
        places,
        llm,
        settings.task_lease_seconds,
        settings.decision_timeout_seconds,
    )
    worker = TaskWorker(
        tasks,
        runner.execute_claim,
        lease_seconds=settings.task_lease_seconds,
        poll_seconds=settings.task_poll_seconds,
        maintenance=tasks.expire_queued,
    )
    return Container(
        auth=auth,
        sessions=sessions,
        worker=worker,
        preference_worker=preference_worker,
        decision_commands=DecisionCommandService(repository),
        decision_queries=queries,
        decision_streams=DecisionStreamService(tasks, queries, auth),
        location=amap,
        places=places,
        preferences=preferences,
        history=HistoryService(HistoryRepository(sessions), queries, places),
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
    async with (
        httpx.AsyncClient(follow_redirects=False) as client,
        AsyncOpenAI(
            api_key=settings.llm_api_key.get_secret_value(),
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        ) as llm_client,
    ):
        try:
            app.state.container = build_container(settings, sessions, client, llm_client)
            app.state.ready = True
            workers = [app.state.container.worker, app.state.container.preference_worker]
            jobs = [asyncio.create_task(worker.run()) for worker in workers]
            try:
                yield
            finally:
                for worker in workers:
                    await worker.stop()
                for job in jobs:
                    job.cancel()
                await asyncio.gather(*jobs, return_exceptions=True)
        finally:
            app.state.ready = False
            await engine_of(sessions).dispose()
