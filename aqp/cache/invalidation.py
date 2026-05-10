"""Synchronous write-through helpers for the metadata cache.

Mutation routes call :func:`cache_write_through` after a successful
Postgres ``commit`` so the next ``ZRANGEBYLEX`` already sees the new
entity. Failures here are logged but never raised — the cache is a
performance / UX optimisation, not the source of truth.

To delete an entity from the cache without touching Postgres, use
:func:`cache_invalidate`.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.cache.client import get_cache
from aqp.cache.keys import (
    CACHE_CATEGORIES,
    by_id_hash,
    by_name_hash,
    names_zset,
)

logger = logging.getLogger(__name__)


def cache_write_through(category: str, payload: dict[str, Any]) -> None:
    """Insert / update a single entity in the cache.

    ``payload`` must include at least ``id`` and ``name``. Other keys
    are stored verbatim in the by_id hash. This helper is idempotent.
    """
    if category not in CACHE_CATEGORIES:
        logger.warning(
            "cache_write_through called with unknown category %r; ignoring", category
        )
        return
    if not isinstance(payload, dict):
        logger.warning("cache_write_through ignored non-dict payload for %s", category)
        return
    identifier = str(payload.get("id") or payload.get("name") or "").strip()
    name = str(payload.get("name") or payload.get("id") or "").strip()
    if not identifier or not name:
        logger.debug(
            "cache_write_through skipped %s payload missing id/name: %s",
            category,
            payload,
        )
        return
    try:
        cache = get_cache()
        with cache.pipeline() as pipe:
            pipe.zadd(names_zset(category), {name: 0.0})
            pipe.hset(by_id_hash(category, identifier), payload)
            pipe.hset(by_name_hash(category, name), {"id": identifier})
    except Exception as exc:  # noqa: BLE001
        logger.warning("cache_write_through(%s, %s) failed: %s", category, identifier, exc)


def cache_invalidate(category: str, identifier: str, *, name: str | None = None) -> None:
    """Drop an entity from the cache.

    ``identifier`` is the row id (the same value passed to
    :func:`cache_write_through`). ``name`` is optional but lets us
    remove the by_name reverse-lookup hash too.
    """
    if category not in CACHE_CATEGORIES:
        logger.warning("cache_invalidate called with unknown category %r", category)
        return
    if not identifier:
        return
    try:
        cache = get_cache()
        cache.delete(by_id_hash(category, identifier))
        if name:
            cache.zrem(names_zset(category), name)
            cache.delete(by_name_hash(category, name))
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "cache_invalidate(%s, %s) failed: %s", category, identifier, exc
        )


__all__ = ["cache_invalidate", "cache_write_through"]
