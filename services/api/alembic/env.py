"""Alembic environment: async engine, `app` schema, models from unisona.models."""
import asyncio

from alembic import context
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from unisona import models  # noqa: F401  (registers tables)
from unisona.config import settings
from unisona.db import Base

config = context.config
target_metadata = Base.metadata
SCHEMA = settings.db_schema


def include_name(name, type_, parent_names):
    if type_ == "schema":
        return name == SCHEMA
    return True


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        include_name=include_name,
        version_table_schema=SCHEMA,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    engine = create_async_engine(settings.async_database_url, connect_args={"statement_cache_size": 0})
    async with engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
        await connection.commit()
    await engine.dispose()


def run_migrations_offline():
    context.configure(url=settings.async_database_url, target_metadata=target_metadata, literal_binds=True,
                      include_schemas=True, version_table_schema=SCHEMA)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
