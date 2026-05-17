"""SQL :class:`BaseDataset`.

Read-only by default (Kedro's ``pandas.SQLQueryDataset`` analogue).
Writes go through Alembic migrations + :class:`LedgerWriter`. The
``connection`` field can be one of:

- ``"postgres"`` (default) — uses the AQP sync engine via
  ``aqp.persistence.db._sync_engine()``.
- A SQLAlchemy URL string — used directly.

Spec config schema::

    {
      "connection": "postgres",     # or a DSN
      "query": "select 1",          # required
      "params": {...},
      "load_args": {...},           # passed to pd.read_sql_query
    }
"""
from __future__ import annotations

from typing import Any

from aqp.data.datasets.base import BaseDataset
from aqp.data.datasets.exceptions import DatasetSaveDisabled


class SQLDataset(BaseDataset):
    kind = "sql"
    writable = False

    def _validate_spec(self) -> None:
        if not str(self._spec.config.get("query") or "").strip():
            raise ValueError("SQLDataset requires config.query")

    def _engine(self) -> Any:
        cfg = self._spec.config
        connection = str(cfg.get("connection") or "postgres").strip().lower()
        if connection in ("postgres", "aqp", "default", ""):
            from aqp.persistence.db import _sync_engine

            return _sync_engine()
        from sqlalchemy import create_engine

        return create_engine(connection, future=True)

    def _load(self) -> Any:
        import pandas as pd

        engine = self._engine()
        cfg = self._spec.config
        load_args = dict(cfg.get("load_args") or {})
        params = cfg.get("params")
        with engine.connect() as conn:
            return pd.read_sql_query(
                str(cfg["query"]),
                conn,
                params=params,
                **load_args,
            )

    def _save(self, payload: Any) -> Any:
        raise DatasetSaveDisabled(
            "SQLDataset is read-only; database writes go through Alembic + LedgerWriter"
        )

    def _exists(self) -> bool:
        return True

    def _describe(self) -> dict[str, Any]:
        cfg = self._spec.config
        query = str(cfg.get("query") or "")
        return {
            "connection": cfg.get("connection") or "postgres",
            "query_preview": query[:120],
            "load_mode": "sql",
        }


__all__ = ["SQLDataset"]
