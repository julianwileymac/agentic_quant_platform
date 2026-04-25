"""SQLAlchemy engine + session factory. Sync for Celery tasks, async for FastAPI.

Engines are created lazily so that merely importing this module does not
require psycopg2/asyncpg to be installed — handy for unit tests that never
touch Postgres.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager, contextmanager
from functools import lru_cache
from typing import Any

from aqp.config import settings


@lru_cache(maxsize=1)
def _sync_engine() -> Any:
    from sqlalchemy import create_engine

    return create_engine(
        settings.postgres_dsn,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        future=True,
    )


@lru_cache(maxsize=1)
def _async_engine() -> Any:
    from sqlalchemy.ext.asyncio import create_async_engine

    return create_async_engine(
        settings.postgres_async_dsn,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        future=True,
    )


class _LazyEngine:
    def __init__(self, factory) -> None:
        self._factory = factory

    def __getattr__(self, name: str) -> Any:
        return getattr(self._factory(), name)

    def __repr__(self) -> str:  # pragma: no cover
        return "<LazyEngine>"

    def connect(self, *a: Any, **kw: Any) -> Any:
        return self._factory().connect(*a, **kw)


engine = _LazyEngine(_sync_engine)
async_engine = _LazyEngine(_async_engine)


@lru_cache(maxsize=1)
def _session_local():
    from sqlalchemy.orm import sessionmaker

    return sessionmaker(bind=_sync_engine(), autocommit=False, autoflush=False, future=True)


@lru_cache(maxsize=1)
def _async_session_local():
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    return async_sessionmaker(bind=_async_engine(), class_=AsyncSession, expire_on_commit=False)


class _SessionLocalProxy:
    def __call__(self, *args: Any, **kwargs: Any):
        return _session_local()(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(_session_local(), name)


class _AsyncSessionLocalProxy:
    def __call__(self, *args: Any, **kwargs: Any):
        return _async_session_local()(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(_async_session_local(), name)


SessionLocal = _SessionLocalProxy()
AsyncSessionLocal = _AsyncSessionLocalProxy()


@contextmanager
def get_session() -> Iterator[Any]:
    session = _session_local()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[Any, None]:
    async with _async_session_local()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def async_session_dep() -> AsyncGenerator[Any, None]:
    """FastAPI dependency."""
    async with _async_session_local()() as session:
        yield session
