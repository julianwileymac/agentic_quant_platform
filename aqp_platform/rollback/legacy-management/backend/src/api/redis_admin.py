"""Redis administration endpoints.

Surfaces the shared Redis 8 Stack deployment via read-only introspection
endpoints (`/api/redis/*`) plus a namespaced cache-invalidation endpoint
that the portal uses to clear hardware / MLflow / Flink caches on
demand.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel

from ..config import Settings, get_settings
from ..services import RedisService

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Shared RedisService singleton (same one used by DocumentService)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _redis_singleton(settings_id: int) -> RedisService:  # noqa: ARG001
    return RedisService(get_settings())


def get_redis_service(settings: Settings = Depends(get_settings)) -> RedisService:
    return _redis_singleton(id(settings))


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------
class RedisHealth(BaseModel):
    enabled: bool
    ping: bool
    modules: dict[str, str]
    missing_modules: list[str] = []
    error: str | None = None


class RedisIndexInfo(BaseModel):
    name: str
    info: dict[str, Any]


class RedisCacheStats(BaseModel):
    counters: dict[str, int]
    prefix: str = "cache:*"


class RedisInvalidateResult(BaseModel):
    namespace: str
    deleted: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/health", response_model=RedisHealth)
async def redis_health(
    service: RedisService = Depends(get_redis_service),
) -> RedisHealth:
    state = await service.health()
    return RedisHealth(**state)


@router.get("/stats")
async def redis_stats(
    service: RedisService = Depends(get_redis_service),
    sections: list[str] | None = Query(default=None, description="INFO sections to include"),
) -> dict[str, Any]:
    info = await service.server_info()
    if sections:
        info = {s: info.get(s, {}) for s in sections}
    return {"info": info, "cache": await service.cache_stats()}


@router.get("/indexes", response_model=list[RedisIndexInfo])
async def redis_indexes(
    service: RedisService = Depends(get_redis_service),
) -> list[RedisIndexInfo]:
    names = await service.list_indexes()
    details: list[RedisIndexInfo] = []
    for name in names:
        info = await service.index_info(name)
        details.append(RedisIndexInfo(name=name, info=info))
    return details


@router.delete("/cache/{namespace}", response_model=RedisInvalidateResult)
async def invalidate_cache_namespace(
    namespace: str = Path(min_length=1, max_length=128),
    service: RedisService = Depends(get_redis_service),
) -> RedisInvalidateResult:
    # Guard against accidentally wiping the entire cache by mistyping `*`.
    if namespace.strip("*") == "":
        raise HTTPException(
            status_code=400,
            detail="Refusing to delete the entire cache via wildcard. "
            "Name a specific namespace like 'hardware' or 'mlflow'.",
        )
    deleted = await service.invalidate_namespace(namespace)
    return RedisInvalidateResult(namespace=namespace, deleted=deleted)
