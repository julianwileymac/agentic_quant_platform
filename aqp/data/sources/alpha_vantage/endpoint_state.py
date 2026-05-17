"""Per-endpoint runtime state (enabled flag, cache TTL override).

Persists to ``DatasetCatalog.meta`` keyed by ``iceberg_identifier`` so a
re-deploy or process restart does not reset the operator's preferences.
Falls back to a process-local dict when the database is unavailable.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from aqp.data.sources.alpha_vantage.catalog import AlphaVantageFunction, get_function
from aqp.persistence.db import get_session
from aqp.persistence.models import DatasetCatalog

logger = logging.getLogger(__name__)


_FALLBACK: dict[str, dict[str, Any]] = {}


def get_state(function_id: str) -> dict[str, Any]:
    fn = get_function(function_id)
    if fn is None:
        return {"enabled_for_bulk": False, "cache_ttl_seconds": None}
    persisted = _read_meta_state(fn)
    if persisted:
        return persisted
    return _FALLBACK.get(function_id, {"enabled_for_bulk": fn.lake_supported, "cache_ttl_seconds": None})


def set_state(function_id: str, *, enabled_for_bulk: bool | None, cache_ttl_seconds: float | None) -> dict[str, Any]:
    fn = get_function(function_id)
    if fn is None:
        return {"enabled_for_bulk": False, "cache_ttl_seconds": None}
    state = get_state(function_id)
    if enabled_for_bulk is not None:
        state["enabled_for_bulk"] = bool(enabled_for_bulk)
    if cache_ttl_seconds is not None:
        state["cache_ttl_seconds"] = float(cache_ttl_seconds)
    _FALLBACK[function_id] = state
    _write_meta_state(fn, state)
    return state


def _read_meta_state(fn: AlphaVantageFunction) -> dict[str, Any] | None:
    if not fn.iceberg_identifier:
        return None
    try:
        with get_session() as session:
            row = session.execute(
                select(DatasetCatalog)
                .where(DatasetCatalog.iceberg_identifier == fn.iceberg_identifier)
                .limit(1)
            ).scalar_one_or_none()
            if row is None or not row.meta:
                return None
            state = (row.meta or {}).get("alpha_vantage_endpoint_state")
            if not isinstance(state, dict):
                return None
            return {
                "enabled_for_bulk": bool(state.get("enabled_for_bulk", fn.lake_supported)),
                "cache_ttl_seconds": state.get("cache_ttl_seconds"),
            }
    except Exception:
        logger.debug("alpha_vantage endpoint state read failed", exc_info=True)
        return None


def _write_meta_state(fn: AlphaVantageFunction, state: dict[str, Any]) -> None:
    if not fn.iceberg_identifier:
        return
    try:
        with get_session() as session:
            row = session.execute(
                select(DatasetCatalog)
                .where(DatasetCatalog.iceberg_identifier == fn.iceberg_identifier)
                .limit(1)
            ).scalar_one_or_none()
            if row is None:
                # Persist a stub row so the state survives restarts even
                # before the first bulk load materializes the table.
                row = DatasetCatalog(
                    name=f"alpha_vantage.{fn.iceberg_table}",
                    provider="alpha_vantage",
                    domain=fn.domain,
                    iceberg_identifier=fn.iceberg_identifier,
                    load_mode="managed",
                    meta={"alpha_vantage_endpoint_state": state},
                )
                session.add(row)
                session.flush()
                return
            meta = dict(row.meta or {})
            meta["alpha_vantage_endpoint_state"] = state
            row.meta = meta
            session.add(row)
            session.flush()
    except Exception:
        logger.debug("alpha_vantage endpoint state write failed", exc_info=True)


__all__ = ["get_state", "set_state"]
