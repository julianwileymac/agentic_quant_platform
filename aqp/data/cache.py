"""Lightweight Redis-backed JSON cache.

The platform already runs Redis for pub/sub (see :mod:`aqp.ws.broker`),
so we reuse that connection for read-through caching of expensive
provider calls (yfinance fundamentals, news, calendar, ...).

Design goals
------------
* **Graceful degrade** — if Redis is down the helpers still return the
  producer result; caching becomes a no-op with a warning.
* **Sync + async** — FastAPI routes are async, Celery tasks are sync.
* **Namespaced keys** — everything lives under ``aqp:cache:<scope>:<key>``
  so callers can flush a whole scope (``security``, ``quote``, ...) on
  demand without stepping on pub/sub channels.
* **Stale-on-error** — if the producer raises *after* a cached value is
  available we return the cached value and log.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from aqp.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

_KEY_PREFIX = "aqp:cache"
_STALE_SUFFIX = ":stale"


def _scoped_key(scope: str, key: str) -> str:
    return f"{_KEY_PREFIX}:{scope}:{key}"


def _stale_key(scope: str, key: str) -> str:
    return _scoped_key(scope, key) + _STALE_SUFFIX


def _serialize(value: Any) -> str:
    return json.dumps(value, default=str, separators=(",", ":"))


def _deserialize(raw: str | bytes | None) -> Any:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(raw)
    except Exception:
        logger.warning("cache: failed to deserialize payload, returning None")
        return None


def _sync_client():  # pragma: no cover - thin wrapper
    try:
        import redis

        return redis.Redis.from_url(settings.redis_url, decode_responses=True)
    except Exception:
        logger.debug("cache: redis sync client unavailable", exc_info=True)
        return None


def _async_client():  # pragma: no cover - thin wrapper
    try:
        import redis.asyncio as aioredis

        return aioredis.from_url(settings.redis_url, decode_responses=True)
    except Exception:
        logger.debug("cache: redis async client unavailable", exc_info=True)
        return None


# --------------------------------------------------------------------------
# Public helpers
# --------------------------------------------------------------------------


def cache_get(scope: str, key: str) -> Any | None:
    """Return cached JSON payload or ``None`` on miss / redis error."""
    client = _sync_client()
    if client is None:
        return None
    try:
        raw = client.get(_scoped_key(scope, key))
    except Exception:
        logger.debug("cache: GET failed for %s/%s", scope, key, exc_info=True)
        return None
    return _deserialize(raw)


def cache_set(scope: str, key: str, value: Any, ttl: int) -> bool:
    """Store ``value`` under ``scope/key`` with ``ttl`` seconds. Returns True on success."""
    client = _sync_client()
    if client is None:
        return False
    try:
        payload = _serialize(value)
    except (TypeError, ValueError):
        logger.warning("cache: value is not JSON serializable for %s/%s", scope, key)
        return False
    try:
        client.setex(_scoped_key(scope, key), ttl, payload)
        # Keep a stale-but-present copy (10x TTL) for stale-on-error fallback.
        client.setex(_stale_key(scope, key), max(ttl * 10, ttl + 60), payload)
        return True
    except Exception:
        logger.debug("cache: SET failed for %s/%s", scope, key, exc_info=True)
        return False


def cache_invalidate(scope: str, key: str | None = None) -> int:
    """Drop one key (or a whole scope when ``key`` is ``None``). Returns count deleted."""
    client = _sync_client()
    if client is None:
        return 0
    try:
        if key is not None:
            return int(
                client.delete(
                    _scoped_key(scope, key),
                    _stale_key(scope, key),
                )
            )
        pattern = f"{_KEY_PREFIX}:{scope}:*"
        cursor = 0
        deleted = 0
        while True:
            cursor, keys = client.scan(cursor=cursor, match=pattern, count=100)
            if keys:
                deleted += int(client.delete(*keys))
            if cursor == 0:
                break
        return deleted
    except Exception:
        logger.debug("cache: invalidate failed for %s/%s", scope, key, exc_info=True)
        return 0


def cached_json_sync(
    scope: str,
    key: str,
    ttl: int,
    producer: Callable[[], Any],
) -> Any:
    """Synchronous read-through cache. Returns producer output; caches on success.

    If the producer raises but a stale copy exists, the stale copy is
    returned and the error is logged.
    """
    hit = cache_get(scope, key)
    if hit is not None:
        return hit
    try:
        fresh = producer()
    except Exception:
        logger.exception("cache: producer failed for %s/%s", scope, key)
        stale = _stale_read(scope, key)
        if stale is not None:
            logger.warning("cache: returning stale copy for %s/%s", scope, key)
            return stale
        raise
    cache_set(scope, key, fresh, ttl)
    return fresh


async def cached_json(
    scope: str,
    key: str,
    ttl: int,
    producer: Callable[[], Awaitable[T] | T],
) -> T:
    """Async read-through cache.

    ``producer`` may be a coroutine function or a regular callable; in
    the latter case it is executed in a worker thread to avoid blocking
    the event loop (yfinance calls are blocking I/O).
    """
    hit = await _async_get(scope, key)
    if hit is not None:
        return hit  # type: ignore[return-value]
    try:
        result = producer()
        if asyncio.iscoroutine(result):
            fresh = await result
        else:
            fresh = await asyncio.to_thread(lambda: result)  # type: ignore[arg-type]
    except Exception:
        logger.exception("cache: async producer failed for %s/%s", scope, key)
        stale = await _async_stale_read(scope, key)
        if stale is not None:
            logger.warning("cache: returning stale copy for %s/%s", scope, key)
            return stale  # type: ignore[return-value]
        raise
    await _async_set(scope, key, fresh, ttl)
    return fresh  # type: ignore[return-value]


# --------------------------------------------------------------------------
# Async Redis helpers (internal)
# --------------------------------------------------------------------------


async def _async_get(scope: str, key: str) -> Any | None:
    client = _async_client()
    if client is None:
        return None
    try:
        raw = await client.get(_scoped_key(scope, key))
    except Exception:
        logger.debug("cache: async GET failed for %s/%s", scope, key, exc_info=True)
        raw = None
    finally:
        try:
            await client.close()
        except Exception:
            pass
    return _deserialize(raw)


async def _async_set(scope: str, key: str, value: Any, ttl: int) -> bool:
    client = _async_client()
    if client is None:
        return False
    try:
        payload = _serialize(value)
    except (TypeError, ValueError):
        logger.warning("cache: value is not JSON serializable for %s/%s", scope, key)
        return False
    try:
        await client.setex(_scoped_key(scope, key), ttl, payload)
        await client.setex(_stale_key(scope, key), max(ttl * 10, ttl + 60), payload)
        return True
    except Exception:
        logger.debug("cache: async SET failed for %s/%s", scope, key, exc_info=True)
        return False
    finally:
        try:
            await client.close()
        except Exception:
            pass


def _stale_read(scope: str, key: str) -> Any | None:
    client = _sync_client()
    if client is None:
        return None
    try:
        return _deserialize(client.get(_stale_key(scope, key)))
    except Exception:
        return None


async def _async_stale_read(scope: str, key: str) -> Any | None:
    client = _async_client()
    if client is None:
        return None
    try:
        raw = await client.get(_stale_key(scope, key))
        return _deserialize(raw)
    except Exception:
        return None
    finally:
        try:
            await client.close()
        except Exception:
            pass


__all__ = [
    "cache_get",
    "cache_set",
    "cache_invalidate",
    "cached_json",
    "cached_json_sync",
]
