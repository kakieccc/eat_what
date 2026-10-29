from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from datetime import timedelta

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import now
from app.core.config import Settings
from app.infrastructure.amap.models import PlaceCache
from app.infrastructure.database.session import create_sessions, engine_of
from app.modules.auth.models import AuthRateLimit, AuthSession
from app.modules.decision.models import IdempotencyRecord

log = logging.getLogger("food.maintenance")
BATCH_SIZE = 1000


async def cleanup(
    sessions: async_sessionmaker[AsyncSession], *, dry_run: bool = False
) -> dict[str, int]:
    cutoff = now()
    counts: dict[str, int] = {}
    for model, column, until in (
        (PlaceCache, PlaceCache.expires_at, cutoff),
        (AuthSession, AuthSession.expires_at, cutoff),
        (IdempotencyRecord, IdempotencyRecord.expires_at, cutoff),
        (AuthRateLimit, AuthRateLimit.window_started_at, cutoff - timedelta(hours=24)),
    ):
        started = time.monotonic()
        count = 0
        try:
            if dry_run:
                async with sessions.begin() as session:
                    await session.execute(text("SET LOCAL statement_timeout = '5s'"))
                    count = await session.scalar(
                        select(func.count()).select_from(model).where(column <= until)
                    ) or 0
            else:
                while True:
                    async with sessions.begin() as session:
                        await session.execute(text("SET LOCAL statement_timeout = '5s'"))
                        expired = (
                            select(model.id).where(column <= until)
                            .order_by(column, model.id).limit(BATCH_SIZE)
                            .with_for_update(skip_locked=True).cte("expired")
                        )
                        removed = await session.scalars(
                            delete(model).where(
                                model.id.in_(select(expired.c.id)), column <= until,
                            ).returning(model.id)
                        )
                        batch_count = len(removed.all())
                    count += batch_count
                    if batch_count == 0:
                        break
        except Exception as error:
            log.error(json.dumps({
                "event": "cleanupFailed", "table": model.__tablename__,
                "deleted": count, "exceptionType": type(error).__name__,
                "durationMs": int((time.monotonic() - started) * 1000),
            }))
            raise
        counts[model.__tablename__] = count
        log.info(json.dumps({
            "event": "cleanupTable", "table": model.__tablename__,
            "dryRun": dry_run, "count": count, "cutoff": until.isoformat(),
            "durationMs": int((time.monotonic() - started) * 1000),
        }))
    return counts


async def run(dry_run: bool) -> None:
    sessions = create_sessions(Settings())
    try:
        await cleanup(sessions, dry_run=dry_run)
    finally:
        await engine_of(sessions).dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Remove expired temporary data.")
    parser.add_argument("--dry-run", action="store_true", help="Count eligible rows without deleting them.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        asyncio.run(run(args.dry_run))
    except Exception as error:
        log.error(json.dumps({"event": "cleanupCommandFailed", "exceptionType": type(error).__name__}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
