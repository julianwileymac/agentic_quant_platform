"""SQLAlchemy engine + session factory. Sync for Celery tasks, async for FastAPI.

Engines are created lazily so that merely importing this module does not
require psycopg2/asyncpg to be installed — handy for unit tests that never
touch Postgres.

Phase 6 §9.4 (RESTRUCTURING_PLAN.md): the engine + sessionmaker caches
are keyed by the active deployment cell. The legacy single-engine path
(no cell context) keys to ``None`` so existing behaviour is preserved
for CLI / bootstrap callers. Cell-bound requests use the per-cell
``CellDataPlane.postgres_dsn_secret`` to build a dedicated engine.

The cell id comes from the existing Phase 3 §6.3 runtime context
(``aqp.tenancy.runtime_context.get_runtime_context``) — there is no
new ContextVar. ASGI middleware populates it on every request; Celery
workers re-populate it from the workload row before each task. PEP 567
guarantees the ContextVar propagates across ``asyncio.create_task``;
thread pool workers must use ``contextvars.copy_context().run(fn)``.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager, contextmanager
from functools import lru_cache
from typing import Any

from aqp.config import settings


# ---------------------------------------------------------------------------
# Phase 6 §9.4 — cell-aware engine / session resolution.
#
# Two helpers wrap the runtime context lookup. Both return ``None`` when
# no cell binding is in effect; that ``None`` key feeds straight into
# the ``@lru_cache``-backed engine factories so the legacy shared
# engine is the default code path.
# ---------------------------------------------------------------------------


def _active_cell_id() -> str | None:
    """Return the active cell id, or ``None`` for the shared/legacy path."""
    try:
        from aqp.tenancy.runtime_context import get_runtime_context
    except Exception:  # pragma: no cover - defensive
        return None
    ctx = get_runtime_context()
    return getattr(ctx, "cell_id", None) if ctx is not None else None


def _cell_postgres_dsn(cell_id: str) -> str | None:
    """Resolve a cell's Postgres DSN, or ``None`` if no per-cell DSN is configured.

    Order of precedence:
      1. ``CellDataPlane.postgres_dsn_secret`` resolved through
         :class:`aqp.credentials.CredentialResolver`.
      2. The cell exists in topology but has no ``postgres_dsn_secret``:
         return ``None`` (caller falls back to ``settings.postgres_dsn``).
      3. The cell id is unknown or the topology cannot be loaded:
         return ``None``.
    """
    try:
        from aqp.deployment.topology import get_deployment_topology
    except Exception:  # pragma: no cover - defensive
        return None
    try:
        topo = get_deployment_topology()
    except Exception:  # pragma: no cover - defensive
        return None
    cell = topo.cell_map.get(cell_id)
    if cell is None:
        return None
    dp = getattr(cell, "data_plane", None)
    if dp is None:
        return None
    secret_path = (getattr(dp, "postgres_dsn_secret", "") or "").strip()
    if not secret_path:
        return None
    # Resolve through the credential resolver. The secret-store
    # implementation owns the actual fetch; we just supply the key.
    try:
        from aqp.credentials import CredentialKey, get_resolver
    except Exception:  # pragma: no cover - defensive
        return None
    creds = get_resolver().resolve(
        CredentialKey("cell-postgres", cell_id),
        default={"dsn": ""},
    )
    dsn = (creds.get("dsn") or "").strip()
    return dsn or None


@lru_cache(maxsize=32)
def _sync_engine_for_cell(cell_id: str | None) -> Any:
    """Per-cell sync SQLAlchemy engine.

    Cell ``None`` is the legacy / shared cluster-wide DSN
    (``settings.postgres_dsn``). Each known cell with a configured
    ``postgres_dsn_secret`` gets its own connection pool keyed by id.
    Cap is 32 entries — LRU eviction is fine; engine teardown closes
    the pool cleanly.
    """
    from sqlalchemy import create_engine

    dsn = settings.postgres_dsn
    if cell_id is not None:
        cell_dsn = _cell_postgres_dsn(cell_id)
        if cell_dsn:
            dsn = cell_dsn
    return create_engine(
        dsn,
        pool_pre_ping=True,
        pool_size=max(1, int(settings.postgres_pool_size)),
        max_overflow=max(0, int(settings.postgres_max_overflow)),
        pool_timeout=max(1, int(settings.postgres_pool_timeout_seconds)),
        pool_recycle=max(60, int(settings.postgres_pool_recycle_seconds)),
        future=True,
    )


@lru_cache(maxsize=32)
def _async_engine_for_cell(cell_id: str | None) -> Any:
    """Per-cell async SQLAlchemy engine (asyncpg)."""
    from sqlalchemy.ext.asyncio import create_async_engine

    dsn = settings.postgres_async_dsn
    if cell_id is not None:
        cell_dsn = _cell_postgres_dsn(cell_id)
        if cell_dsn:
            # The async DSN is the sync DSN with ``+asyncpg``. We use
            # the resolver's ``async_dsn`` field if present, otherwise
            # mechanically translate ``postgresql://`` to
            # ``postgresql+asyncpg://``.
            try:
                from aqp.credentials import CredentialKey, get_resolver
            except Exception:  # pragma: no cover - defensive
                dsn = cell_dsn
            else:
                creds = get_resolver().resolve(
                    CredentialKey("cell-postgres", cell_id),
                    default={"async_dsn": ""},
                )
                async_dsn = (creds.get("async_dsn") or "").strip()
                if async_dsn:
                    dsn = async_dsn
                else:
                    dsn = cell_dsn.replace(
                        "postgresql://", "postgresql+asyncpg://", 1
                    )
    return create_async_engine(
        dsn,
        pool_pre_ping=True,
        pool_size=max(1, int(settings.postgres_pool_size)),
        max_overflow=max(0, int(settings.postgres_max_overflow)),
        pool_timeout=max(1, int(settings.postgres_pool_timeout_seconds)),
        pool_recycle=max(60, int(settings.postgres_pool_recycle_seconds)),
        future=True,
    )


def _sync_engine() -> Any:
    """Return the active engine (cell-keyed)."""
    return _sync_engine_for_cell(_active_cell_id())


def _async_engine() -> Any:
    return _async_engine_for_cell(_active_cell_id())


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


@lru_cache(maxsize=32)
def _session_local_for_cell(cell_id: str | None):
    """Per-cell sessionmaker bound to the per-cell sync engine."""
    from sqlalchemy.orm import sessionmaker

    return sessionmaker(
        bind=_sync_engine_for_cell(cell_id),
        autocommit=False,
        autoflush=False,
        future=True,
    )


@lru_cache(maxsize=32)
def _async_session_local_for_cell(cell_id: str | None):
    """Per-cell async sessionmaker bound to the per-cell async engine."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    return async_sessionmaker(
        bind=_async_engine_for_cell(cell_id),
        class_=AsyncSession,
        expire_on_commit=False,
    )


def _session_local():
    """Return the active sessionmaker (cell-keyed)."""
    return _session_local_for_cell(_active_cell_id())


def _async_session_local():
    return _async_session_local_for_cell(_active_cell_id())


def reset_engine_cache() -> None:
    """Invalidate every cell-keyed engine + sessionmaker (used by tests).

    Phase 6 §9.4 — closes the underlying connection pools too. Safe to
    call at any time; subsequent calls re-create the engine on demand.
    """
    for fn in (
        _sync_engine_for_cell,
        _async_engine_for_cell,
        _session_local_for_cell,
        _async_session_local_for_cell,
    ):
        cache_clear = getattr(fn, "cache_clear", None)
        if callable(cache_clear):
            cache_clear()


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
