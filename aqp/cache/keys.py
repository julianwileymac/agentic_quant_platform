"""Single source of truth for metadata cache key names.

Keys must NEVER be hand-constructed elsewhere — always import the
helper from this module. The category vocabulary is fixed: adding a
new category means adding a constant + helper here, then teaching
:class:`aqp.cache.prefetch.MetadataPrefetcher` how to populate it.

Naming convention::

    {prefix}:{category}:names           Sorted set, lexicographically ordered
    {prefix}:{category}:by_id:{id}      Hash, full payload by id
    {prefix}:{category}:by_name:{name}  Optional reverse lookup, hash

``prefix`` defaults to ``aqp:cache`` via
:attr:`aqp.config.settings.Settings.cache_key_prefix` and is included
verbatim in every key so namespace collisions with other AQP Redis
users (RAG vector indexes under ``aqp:rag``, episodic memory, the
Celery progress bus) are impossible.
"""
from __future__ import annotations

from typing import Final

from aqp.config import settings

# ---------------------------------------------------------------- categories

#: Categories supported by the prefetcher. Extending the cache requires
#: adding a literal here AND a populator in
#: :class:`aqp.cache.prefetch.MetadataPrefetcher`.
CACHE_CATEGORIES: Final[tuple[str, ...]] = (
    "datasets",
    "namespaces",
    "sink_kinds",
    "sink_names",
    "airbyte_connectors",
    "projects",
    "credentials",
    "dataset_kinds",
)


def _prefix() -> str:
    """Return the configured cache prefix without trailing colon."""
    return str(getattr(settings, "cache_key_prefix", "aqp:cache")).rstrip(":")


def names_zset(category: str) -> str:
    """Sorted-set key holding lexicographically ordered names for ``category``."""
    if category not in CACHE_CATEGORIES:
        raise ValueError(
            f"unknown cache category {category!r}; expected one of "
            f"{CACHE_CATEGORIES}"
        )
    return f"{_prefix()}:{category}:names"


def by_id_hash(category: str, identifier: str) -> str:
    """Hash key holding the full payload of a single entity."""
    if category not in CACHE_CATEGORIES:
        raise ValueError(f"unknown cache category {category!r}")
    if not identifier:
        raise ValueError("identifier cannot be empty")
    return f"{_prefix()}:{category}:by_id:{identifier}"


def by_name_hash(category: str, name: str) -> str:
    """Optional reverse-lookup hash keyed by name."""
    if category not in CACHE_CATEGORIES:
        raise ValueError(f"unknown cache category {category!r}")
    if not name:
        raise ValueError("name cannot be empty")
    return f"{_prefix()}:{category}:by_name:{name.lower()}"


def fulltext_index(category: str) -> str:
    """RediSearch index name used by :mod:`aqp.cache.search`."""
    if category not in CACHE_CATEGORIES:
        raise ValueError(f"unknown cache category {category!r}")
    return f"{_prefix()}:idx:{category}"


def category_stamp(category: str) -> str:
    """Per-category timestamp key used to expose cache freshness via ``/cache/health``."""
    if category not in CACHE_CATEGORIES:
        raise ValueError(f"unknown cache category {category!r}")
    return f"{_prefix()}:stamp:{category}"


__all__ = [
    "CACHE_CATEGORIES",
    "by_id_hash",
    "by_name_hash",
    "category_stamp",
    "fulltext_index",
    "names_zset",
]
