"""Celery tasks for the metadata cache layer.

The cache is normally kept live by :func:`aqp.cache.cache_write_through`
calls fired from mutation routes. ``refresh_metadata`` is the safety
net: a periodic full rebuild from Postgres + the dataset-kind registry
that heals any drift caused by missed write-throughs, expired keys
without a subsequent read, or a Redis flush.

The task is idempotent and safe to run while the API is serving — the
prefetcher batches per-category replacements behind a single ``DELETE +
ZADD`` so readers never see a partial set.

Wired into :mod:`aqp.tasks.celery_app` ``beat_schedule`` keyed off
:attr:`Settings.cache_refresh_interval_s` (default 5 min). Per-tenant
expansion (Phase 5) will fan out into ``refresh_metadata_for_org``.
"""
from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

from aqp.config import settings

logger = logging.getLogger(__name__)


@shared_task(
    name="aqp.tasks.cache_tasks.refresh_metadata",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def refresh_metadata(self, *, categories: list[str] | None = None) -> dict[str, Any]:
    """Rebuild the metadata cache from authoritative sources.

    Returns ``{category: row_count}`` for the categories touched. Safe
    to call when Postgres or Redis are unreachable — the prefetcher
    degrades to the in-memory fallback / no-op respectively.

    Parameters
    ----------
    categories
        Optional whitelist; when ``None`` every category in
        :data:`aqp.cache.keys.CACHE_CATEGORIES` is refreshed (the
        normal case).
    """
    if not getattr(settings, "cache_enabled", True):
        logger.debug("cache_tasks.refresh_metadata skipped: cache disabled")
        return {"skipped": True}

    from aqp.cache.prefetch import MetadataPrefetcher

    prefetcher = MetadataPrefetcher()
    counts = prefetcher.run_full()
    if categories:
        counts = {k: v for k, v in counts.items() if k in set(categories)}
    logger.info("cache_tasks.refresh_metadata done: %s", counts)
    return counts


__all__ = ["refresh_metadata"]
