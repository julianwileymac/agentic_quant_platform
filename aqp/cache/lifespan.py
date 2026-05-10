"""FastAPI lifespan helpers for the metadata cache.

Keeps the cache "warm" on first request: prefetches the eight cache
categories on startup, optionally creates the RediSearch full-text
index, and logs the result. Failures are non-fatal — the API still
boots even when Redis is offline (the in-memory fallback handles
every read).
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.cache.client import cache_iter_categories, get_cache
from aqp.cache.keys import CACHE_CATEGORIES
from aqp.cache.prefetch import MetadataPrefetcher
from aqp.cache.search import try_create_full_text_index
from aqp.config import settings

logger = logging.getLogger(__name__)


def prefetch_at_startup() -> dict[str, Any]:
    """Run a single full prefetch + try to create the RediSearch index."""
    if not getattr(settings, "cache_enabled", True):
        logger.info("metadata cache disabled; skipping startup prefetch")
        return {"enabled": False}
    cache = get_cache()
    try:
        prefetcher = MetadataPrefetcher(cache=cache)
        counts = prefetcher.run_full()
    except Exception:  # noqa: BLE001
        logger.exception("metadata cache startup prefetch failed; cache may be empty")
        counts = {category: 0 for category in CACHE_CATEGORIES}
    try:
        ft_status = try_create_full_text_index(cache)
    except Exception:  # noqa: BLE001
        logger.exception("metadata cache full-text index attempt failed")
        ft_status = {}
    summary = {
        "enabled": True,
        "remote": cache.is_remote,
        "counts": counts,
        "members": cache_iter_categories(cache, CACHE_CATEGORIES),
        "fulltext": ft_status,
    }
    logger.info(
        "metadata cache prefetch complete remote=%s counts=%s",
        cache.is_remote,
        counts,
    )
    return summary


__all__ = ["prefetch_at_startup"]
