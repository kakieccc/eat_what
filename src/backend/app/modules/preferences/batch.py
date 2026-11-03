from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time

from openai import AsyncOpenAI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.ids import lock_id
from app.infrastructure.database.session import create_sessions, engine_of
from app.infrastructure.llm.provider import OpenAICompatibleLlm
from app.modules.decision.ports import StructuredLlm
from app.modules.preferences.learning import PreferenceLearner
from app.modules.preferences.repository import PreferencesRepository
from app.modules.task.errors import LostTaskLease
from app.modules.task.service import TaskWorker

log = logging.getLogger("food.preferences")
BATCH_LOCK = lock_id("preferences:daily-learning")


async def run_batch(
    sessions: async_sessionmaker[AsyncSession], llm: StructuredLlm, lease_seconds: int
) -> dict[str, int]:
    counts = {"succeeded": 0, "failed": 0, "skipped": 0}
    started = time.monotonic()
    repository = PreferencesRepository(sessions)
    worker = TaskWorker(repository, PreferenceLearner(repository, llm), lease_seconds=lease_seconds)
    # A session advisory lock needs this connection held until the entire batch finishes.
    async with engine_of(sessions).connect() as connection:
        acquired = await connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": BATCH_LOCK})
        await connection.commit()
        if not acquired:
            log.info(json.dumps({"event": "preferenceBatchSkipped", "reason": "alreadyRunning"}))
            return counts
        try:
            # Snapshot once so new triggers cannot keep this scheduled invocation running forever.
            preference_ids = await repository.pending_ids()
            for preference_id in preference_ids:
                try:
                    claim = await repository.claim(lease_seconds, preference_id=preference_id)
                    if claim is None:
                        counts["skipped"] += 1
                        continue
                    succeeded = await worker.execute(claim)
                    counts["succeeded" if succeeded else "failed"] += 1
                except LostTaskLease:
                    counts["skipped"] += 1
                except Exception as error:
                    counts["failed"] += 1
                    log.error(json.dumps({
                        "event": "preferenceLearningFailed", "preferenceId": preference_id,
                        "exceptionType": type(error).__name__,
                    }))
        finally:
            await connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": BATCH_LOCK})
            await connection.commit()
    log.info(json.dumps({
        "event": "preferenceBatchCompleted", **counts,
        "durationMs": int((time.monotonic() - started) * 1000),
    }))
    return counts


async def run() -> bool:
    settings = Settings()
    sessions = create_sessions(settings)
    try:
        async with AsyncOpenAI(
            api_key=settings.llm_api_key.get_secret_value(),
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        ) as client:
            counts = await run_batch(
                sessions, OpenAICompatibleLlm(settings, client), settings.task_lease_seconds,
            )
            return counts["failed"] == 0
    finally:
        await engine_of(sessions).dispose()


def main() -> int:
    argparse.ArgumentParser(description="Run one batch of pending preference learning.").parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for name in ("httpx", "httpcore", "openai"):
        logging.getLogger(name).setLevel(logging.WARNING)
    try:
        return 0 if asyncio.run(run()) else 1
    except Exception as error:
        log.error(json.dumps({"event": "preferenceBatchFailed", "exceptionType": type(error).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
