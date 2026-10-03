"""Async SQLAlchemy engine/session and small tenancy helpers.

All tables live in the `app` schema (settings.db_schema). Supabase only exposes the
`public` schema through its REST Data API, so nothing here is reachable with the
publishable key: every read and write goes through this backend, which scopes each
query to the caller's workspace.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings

metadata = MetaData(schema=settings.db_schema)


class Base(DeclarativeBase):
    metadata = metadata


engine = create_async_engine(
    settings.async_database_url,
    pool_size=8,
    max_overflow=6,
    pool_pre_ping=False,  # each pre-ping is a full round-trip to the remote DB; recycle instead
    pool_recycle=240,
    connect_args={"statement_cache_size": 0, "server_settings": {"application_name": "unisona-api"}},
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
