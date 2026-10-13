from __future__ import annotations

import argparse
import asyncio
from importlib import import_module

from sqlalchemy import Connection, MetaData
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.infrastructure.database.base import Base
from app.infrastructure.database.session import create_sessions, engine_of

for module in (
    "app.modules.auth.models",
    "app.modules.decision.models",
    "app.modules.preferences.models",
    "app.modules.choice.models",
    "app.modules.task.models",
    "app.infrastructure.amap.models",
):
    import_module(module)


def drop_tables(connection: Connection) -> None:
    existing = MetaData()
    existing.reflect(bind=connection)
    existing.drop_all(bind=connection)


async def create_tables(engine: AsyncEngine, *, rebuild: bool = False) -> None:
    async with engine.begin() as connection:
        if rebuild:
            await connection.run_sync(drop_tables)
        await connection.run_sync(Base.metadata.create_all)


async def main(rebuild: bool) -> None:
    engine = engine_of(create_sessions(Settings()))
    try:
        await create_tables(engine, rebuild=rebuild)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create development database tables.")
    parser.add_argument(
        "--rebuild", action="store_true",
        help="Delete all tables and data in the current schema, then create the current models.",
    )
    args = parser.parse_args()
    asyncio.run(main(args.rebuild))
