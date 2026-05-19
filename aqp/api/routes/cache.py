"""Read-only metadata cache endpoints.

Backs the :file:`frontend/src/components/common/EntityPicker.tsx`
component. Whitelist-only entity dropdowns read from these endpoints
and are guaranteed sub-millisecond when Redis is reachable; the
in-memory fallback keeps unit tests + the local dev loop honest.

Mutations don't live here — they happen on the canonical surfaces
(``/metadata-catalog/datasets``, ``/airbyte/connections``,
``/sinks``, etc.) and call
:func:`aqp.cache.invalidation.cache_write_through` after the
Postgres commit.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from aqp.api.security import secure_router
from aqp.cache.client import cache_iter_categories, get_cache
from aqp.cache.keys import (
    CACHE_CATEGORIES,
    by_id_hash,
    by_name_hash,
    category_stamp,
    names_zset,
)

router = secure_router(prefix="/cache", tags=["cache"], default_scope="data:read")


class CacheNamePage(BaseModel):
    """Paged response shape for ``GET /cache/<category>``."""

    category: str
    items: list[dict[str, Any]] = Field(default_factory=list)
    next_cursor: int | None = None
    total: int = 0


class CacheHealth(BaseModel):
    """Diagnostic snapshot exposed via ``GET /cache/health``."""

    enabled: bool
    remote: bool
    members: dict[str, int] = Field(default_factory=dict)
    stamps: dict[str, str | None] = Field(default_factory=dict)
    info: dict[str, Any] = Field(default_factory=dict)


def _validate_category(category: str) -> str:
    if category not in CACHE_CATEGORIES:
        raise HTTPException(
            status_code=404,
            detail=f"unknown cache category {category!r}; expected one of {CACHE_CATEGORIES}",
        )
    return category


def _resolve_member(
    cache: Any, category: str, member: str
) -> dict[str, Any]:
    """Hydrate a member into its full payload via reverse-lookup hash."""
    base = {"name": member, "id": member}
    by_name = cache.hgetall(by_name_hash(category, member))
    if isinstance(by_name, dict):
        identifier = str(by_name.get("id") or member)
        base["id"] = identifier
        if identifier and identifier != member:
            payload = cache.hgetall(by_id_hash(category, identifier))
            if payload:
                base.update(payload)
                return base
    payload = cache.hgetall(by_id_hash(category, member))
    if payload:
        base.update(payload)
    return base


def _list_category(
    category: str,
    *,
    prefix: str,
    cursor: int,
    limit: int,
) -> CacheNamePage:
    cache = get_cache()
    zkey = names_zset(category)
    members = cache.zrange_lex(
        zkey,
        prefix=prefix or "",
        offset=max(0, int(cursor)),
        count=max(1, int(limit)),
    )
    total = cache.zcard(zkey)
    items = [_resolve_member(cache, category, m) for m in members]
    next_cursor: int | None = None
    consumed = max(0, int(cursor)) + len(items)
    if consumed < total and len(items) >= int(limit):
        next_cursor = consumed
    return CacheNamePage(
        category=category,
        items=items,
        next_cursor=next_cursor,
        total=total,
    )


@router.get("/health", response_model=CacheHealth)
def health() -> CacheHealth:
    cache = get_cache()
    members = cache_iter_categories(cache, CACHE_CATEGORIES)
    stamps: dict[str, str | None] = {}
    for category in CACHE_CATEGORIES:
        try:
            stamps[category] = cache.get_string(category_stamp(category))
        except Exception:  # noqa: BLE001
            stamps[category] = None
    return CacheHealth(
        enabled=True,
        remote=cache.is_remote,
        members=dict(members),
        stamps=stamps,
        info=cache.info(),
    )


@router.get("/refresh")
def refresh() -> dict[str, Any]:
    """Trigger a synchronous full prefetch (admin / dev tool)."""
    from aqp.cache.lifespan import prefetch_at_startup

    return prefetch_at_startup()


@router.get("/{category}", response_model=CacheNamePage)
def list_entities(
    category: str,
    prefix: str = Query(default="", max_length=120),
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
) -> CacheNamePage:
    return _list_category(_validate_category(category), prefix=prefix, cursor=cursor, limit=limit)


@router.get("/{category}/{identifier}")
def describe_entity(category: str, identifier: str) -> dict[str, Any]:
    _validate_category(category)
    cache = get_cache()
    payload = cache.hgetall(by_id_hash(category, identifier))
    if not payload:
        # Try reverse lookup by name -> id
        by_name = cache.hgetall(by_name_hash(category, identifier))
        rev_id = (by_name or {}).get("id") if isinstance(by_name, dict) else None
        if rev_id:
            payload = cache.hgetall(by_id_hash(category, str(rev_id)))
    if not payload:
        raise HTTPException(
            status_code=404,
            detail=f"{category} entry {identifier!r} not in cache",
        )
    return payload
