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
    # Original (data fabric phase 0)
    "datasets",
    "namespaces",
    "sink_kinds",
    "sink_names",
    "airbyte_connectors",
    "projects",
    "credentials",
    "dataset_kinds",
    # Tenancy (Phase 5 multi-tenant rollout)
    "organizations",
    "teams",
    "users",
    "workspaces",
    "labs",
    "experiments",
    "tests",
    # Specs (Phase 5)
    "agents",
    "bots",
    "rl_experiments",
    "analysis_specs",
    # Orchestration control plane (additive refactor, Phase 5)
    "workflows",
    # Polymorphic content + LEAN templates (Phase 5 + Phase 7)
    "strategy_templates",
    "resources",
    # pgvector control plane (Phase 3 refactor) — whitelist of vector
    # indexes the frontend EntityPicker can offer; corresponds 1:1 to
    # the pgvector tables created by alembic 0045.
    "vector_indexes",
    # Aspect-driven Iceberg namespace prefix policies.
    "namespace_policies",
)


#: Categories that get an org-id prefix in their Redis key namespace so
#: org_A's dropdown never leaks org_B's rows. The prefix is applied by
#: :func:`names_zset` / :func:`by_id_hash` / :func:`by_name_hash` when
#: a non-empty ``org_id`` is passed.
ORG_SCOPED_CATEGORIES: Final[frozenset[str]] = frozenset(
    {
        "datasets",
        "sink_names",
        "projects",
        "workspaces",
        "labs",
        "experiments",
        "tests",
        "agents",
        "bots",
        "rl_experiments",
        "analysis_specs",
        "workflows",
        "resources",
    }
)


def _prefix() -> str:
    """Return the configured cache prefix without trailing colon."""
    return str(getattr(settings, "cache_key_prefix", "aqp:cache")).rstrip(":")


def _scope_segment(category: str, org_id: str | None) -> str:
    """Build the per-org segment when *category* is org-scoped.

    Returns ``""`` (no segment) for global categories, or ``":{org}"``
    when the category is in :data:`ORG_SCOPED_CATEGORIES` and an
    ``org_id`` is provided. Falls back to ``""`` when ``org_id`` is
    empty so the global fallback (used in unit tests / pre-multi-tenant
    deployments) still works.
    """
    if not org_id:
        return ""
    if category not in ORG_SCOPED_CATEGORIES:
        return ""
    return f":{org_id}"


def names_zset(category: str, *, org_id: str | None = None) -> str:
    """Sorted-set key holding lexicographically ordered names for ``category``."""
    if category not in CACHE_CATEGORIES:
        raise ValueError(
            f"unknown cache category {category!r}; expected one of "
            f"{CACHE_CATEGORIES}"
        )
    return f"{_prefix()}{_scope_segment(category, org_id)}:{category}:names"


def by_id_hash(category: str, identifier: str, *, org_id: str | None = None) -> str:
    """Hash key holding the full payload of a single entity."""
    if category not in CACHE_CATEGORIES:
        raise ValueError(f"unknown cache category {category!r}")
    if not identifier:
        raise ValueError("identifier cannot be empty")
    return f"{_prefix()}{_scope_segment(category, org_id)}:{category}:by_id:{identifier}"


def by_name_hash(category: str, name: str, *, org_id: str | None = None) -> str:
    """Optional reverse-lookup hash keyed by name."""
    if category not in CACHE_CATEGORIES:
        raise ValueError(f"unknown cache category {category!r}")
    if not name:
        raise ValueError("name cannot be empty")
    return f"{_prefix()}{_scope_segment(category, org_id)}:{category}:by_name:{name.lower()}"


def fulltext_index(category: str, *, org_id: str | None = None) -> str:
    """RediSearch index name used by :mod:`aqp.cache.search`."""
    if category not in CACHE_CATEGORIES:
        raise ValueError(f"unknown cache category {category!r}")
    return f"{_prefix()}{_scope_segment(category, org_id)}:idx:{category}"


def category_stamp(category: str, *, org_id: str | None = None) -> str:
    """Per-category timestamp key used to expose cache freshness via ``/cache/health``."""
    if category not in CACHE_CATEGORIES:
        raise ValueError(f"unknown cache category {category!r}")
    return f"{_prefix()}{_scope_segment(category, org_id)}:stamp:{category}"


__all__ = [
    "CACHE_CATEGORIES",
    "ORG_SCOPED_CATEGORIES",
    "by_id_hash",
    "by_name_hash",
    "category_stamp",
    "fulltext_index",
    "names_zset",
]
