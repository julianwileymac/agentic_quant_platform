"""Metadata prefetch cache for the AQP data fabric.

Phase 0 of the self-service data fabric expansion. The cache is the
single read path for **entity dropdowns** in the frontend — datasets,
namespaces, sink kinds, Airbyte connectors, projects, credentials, and
dataset kinds. Free-text inputs that name an entity are forbidden in
new code; the ``EntityPicker`` React component reads from
``/cache/...`` endpoints which in turn read from this layer.

Public surface:

- :class:`MetadataCache` — Redis client wrapper with sorted-set + hash
  helpers and an in-memory fallback when Redis is unreachable.
- :func:`get_cache` — process-wide cached :class:`MetadataCache`.
- :class:`MetadataPrefetcher` — startup + periodic worker that walks
  Postgres + the dataset-kind registry and populates the cache.
- :func:`cache_write_through` / :func:`cache_invalidate` — synchronous
  helpers wired into mutation routes so the cache stays consistent
  without waiting for the next prefetch cycle.

Architecture notes live in :mod:`docs/metadata-cache.md`. The Cursor
rule that scopes this package is :file:`.cursor/rules/cache.mdc`.
"""
from __future__ import annotations

from aqp.cache.client import MetadataCache, get_cache
from aqp.cache.invalidation import cache_invalidate, cache_write_through
from aqp.cache.prefetch import MetadataPrefetcher

__all__ = [
    "MetadataCache",
    "MetadataPrefetcher",
    "cache_invalidate",
    "cache_write_through",
    "get_cache",
]
