from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from dotenv import dotenv_values
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.infrastructure.persistence.models import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

database_url = os.environ.get("DATABASE_URL") or dotenv_values(".env").get("DATABASE_URL")
if not database_url:
    raise RuntimeError("DATABASE_URL is required for migrations")
config.set_main_option("sqlalchemy.url", str(database_url).replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: object) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
