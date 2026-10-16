from __future__ import annotations

import asyncio
import logging

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings
from app.infrastructure.database.metadata import metadata

config = context.config
logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")


def run_migrations_offline() -> None:
    context.configure(
        url=Settings().db_url,
        target_metadata=metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(Settings().db_url, poolclass=pool.NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
elif connection := config.attributes.get("connection"):
    run_migrations(connection)
else:
    asyncio.run(run_migrations_online())
