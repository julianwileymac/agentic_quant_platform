"""Async QuestDB PGWire client.

QuestDB exposes the PostgreSQL wire protocol on port 8812. We wrap
``asyncpg`` so every read in :mod:`aqp.tasks` / :mod:`aqp.api.routes`
goes through one connection-pooled, parameter-binding-safe surface
that respects ``settings.questdb_pg_url`` (resolved through
:mod:`aqp.config.topology_fallback` from the topology service when the
``AQP_QUESTDB_PG_URL`` env var is unset).

DDL queries (``CREATE TABLE ... PARTITION BY HOUR``, etc.) execute
through the same client. The dataset kind in
:mod:`aqp.data.datasets.kinds.questdb` and the ``data.timeseries.questdb.*``
MCP tools both use this client; nothing else in AQP code is allowed
to ``import asyncpg`` against the QuestDB endpoint directly so the
connection pool stays the single bottleneck (rule 9 logging contract,
rule 22 DataMCP boundary).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from aqp.config import settings

logger = logging.getLogger(__name__)


class QuestDBUnavailableError(RuntimeError):
    """Raised when ``asyncpg`` is missing or the QuestDB DSN is unset."""


class QuestDBQueryError(RuntimeError):
    """Raised when a QuestDB SQL query fails."""


class QuestDBClient:
    """Async, connection-pooled QuestDB PGWire client.

    Construction is cheap; connection establishment happens lazily on
    first :meth:`fetch` / :meth:`execute` call. Use :meth:`close` to
    release the pool on shutdown.
    """

    def __init__(self, dsn: str | None = None, *, min_size: int = 1, max_size: int = 8) -> None:
        self._dsn = dsn or settings.questdb_pg_url
        self._min_size = min_size
        self._max_size = max_size
        self._pool: Any | None = None
        self._lock = asyncio.Lock()

    @property
    def dsn(self) -> str:
        return self._dsn

    async def _get_pool(self) -> Any:
        if self._pool is not None:
            return self._pool
        async with self._lock:
            if self._pool is not None:
                return self._pool
            if not self._dsn:
                raise QuestDBUnavailableError(
                    "questdb_pg_url is unset; configure AQP_QUESTDB_PG_URL or "
                    "topology services > questdb > endpoints.pgwire"
                )
            try:
                import asyncpg  # type: ignore[import]
            except ImportError as exc:
                raise QuestDBUnavailableError(
                    "asyncpg is not installed; pip install asyncpg"
                ) from exc
            try:
                self._pool = await asyncpg.create_pool(
                    self._dsn,
                    min_size=self._min_size,
                    max_size=self._max_size,
                    statement_cache_size=0,  # QuestDB does not support prepared cache
                )
            except Exception as exc:  # noqa: BLE001
                raise QuestDBUnavailableError(
                    f"failed to connect to QuestDB at {self._dsn!r}: {exc}"
                ) from exc
            return self._pool

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        """Run ``sql`` and return rows as a list of dicts."""
        pool = await self._get_pool()
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(sql, *args)
        except Exception as exc:  # noqa: BLE001
            raise QuestDBQueryError(f"QuestDB fetch failed: {exc}") from exc
        return [dict(row) for row in rows]

    async def fetch_arrow(self, sql: str, *args: Any) -> Any:
        """Run ``sql`` and return a PyArrow Table for downstream analytics."""
        rows = await self.fetch(sql, *args)
        try:
            import pyarrow as pa
        except ImportError as exc:
            raise QuestDBUnavailableError(
                "pyarrow is required for fetch_arrow; pip install pyarrow"
            ) from exc
        if not rows:
            return pa.table({})
        # asyncpg returns dicts whose values are already Python natives.
        return pa.Table.from_pylist(rows)

    async def execute(self, sql: str, *args: Any) -> str:
        """Run a non-returning SQL statement (DDL / INSERT)."""
        pool = await self._get_pool()
        try:
            async with pool.acquire() as conn:
                return await conn.execute(sql, *args)
        except Exception as exc:  # noqa: BLE001
            raise QuestDBQueryError(f"QuestDB execute failed: {exc}") from exc

    async def list_tables(self) -> list[dict[str, Any]]:
        """Return every QuestDB table with partitioning + size metadata."""
        return await self.fetch("SELECT * FROM tables();")

    async def partition_info(self, table: str) -> list[dict[str, Any]]:
        """Return per-partition rowcount + min/max timestamp for ``table``."""
        # QuestDB exposes partition metadata via the ``table_partitions``
        # built-in. The ``%I`` style escape isn't supported by asyncpg's
        # parameter binding; the table name is whitelisted by the caller
        # (the MCP tool restricts callers to known tables).
        sql = "SELECT * FROM table_partitions(:table);".replace(":table", repr(table))
        return await self.fetch(sql)

    async def sample_by(
        self,
        *,
        table: str,
        ts_column: str,
        bucket: str,
        agg_columns: list[str],
        where: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Run a SAMPLE BY downsampling query.

        QuestDB-native syntax for trailing windows; the agent surface
        composes the SQL safely - column names are whitelisted by the
        caller MCP tool.
        """
        cols = ", ".join(agg_columns) if agg_columns else "*"
        sql = (
            f"SELECT {ts_column}, {cols} FROM {table}"
            f"{' WHERE ' + where if where else ''}"
            f" SAMPLE BY {bucket} LIMIT {int(limit)};"
        )
        return await self.fetch(sql)

    async def close(self) -> None:
        """Drop the connection pool."""
        async with self._lock:
            if self._pool is None:
                return
            try:
                await self._pool.close()
            except Exception:  # noqa: BLE001
                logger.warning("QuestDB pool close raised", exc_info=True)
            self._pool = None


_singleton: QuestDBClient | None = None
_singleton_lock = asyncio.Lock()


async def get_questdb_client() -> QuestDBClient:
    """Return the cached process-wide QuestDB client."""
    global _singleton
    if _singleton is not None:
        return _singleton
    async with _singleton_lock:
        if _singleton is None:
            _singleton = QuestDBClient()
        return _singleton


__all__ = [
    "QuestDBClient",
    "QuestDBQueryError",
    "QuestDBUnavailableError",
    "get_questdb_client",
]
