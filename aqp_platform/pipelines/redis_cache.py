"""Caching primitives backed by the shared Redis 8 Stack.

Three complementary patterns live here:

    1. ``cache_aside`` - a string-keyed cache-aside decorator using
       SHA-256 of the JSON-serialized call arguments.  Mirrors the
       ``microservices-ecommerce-solutions`` tutorial and the plan's
       Redis-for-Query-Caching use case.

    2. ``SemanticCache`` - a wrapper around the RedisVL semantic cache
       extension.  Degrades gracefully to a no-op fake when RedisVL is
       not installed; this means pipelines that do not need semantic
       caching do not carry the transitive dependencies.

    3. ``InvalidationHelper`` - prefix-based invalidation helpers used
       by the management-api admin routes.

Every call here uses ``redis_io.redis_span`` so the Grafana Redis
dashboard sees traffic and the Prometheus histograms populate.
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from .config import get_redis_settings
from .redis_io import (
    get_redis,
    key,
    record_cache_event,
    record_timeseries,
    redis_span,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Key builder
# ---------------------------------------------------------------------------
def build_cache_key(module: str, fn_name: str, args: tuple, kwargs: dict, prefix: str | None = None) -> str:
    """Build a stable SHA-256 cache key from a function call signature."""
    payload = {
        "fn": f"{module}.{fn_name}",
        "args": args,
        "kwargs": kwargs,
    }
    try:
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
    except (TypeError, ValueError):
        digest = hashlib.sha256(repr(payload).encode("utf-8")).hexdigest()
    return key("cache", module, fn_name, digest, prefix=prefix or "rpi")


# ---------------------------------------------------------------------------
# Sync cache-aside decorator
# ---------------------------------------------------------------------------
def cache_aside(
    ttl: int | None = None,
    *,
    namespace: str | None = None,
    key_builder: Callable[..., str] | None = None,
    serialize: Callable[[Any], str] = lambda v: json.dumps(v, default=str),
    deserialize: Callable[[str], Any] = json.loads,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator implementing the cache-aside pattern against Redis.

    Usage::

        @cache_aside(ttl=60)
        def expensive_lookup(symbol: str) -> dict: ...

    The decorator silently no-ops if Redis is unreachable so callers
    never have to guard against cache failures; misses log at debug
    level and observe the `stats:cache` counters.
    """
    effective_ttl = ttl if ttl is not None else get_redis_settings().cache_ttl_seconds

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        mod = namespace or fn.__module__

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            cache_key = (
                key_builder(fn, args, kwargs) if key_builder else
                build_cache_key(mod, fn.__name__, args, kwargs)
            )
            client = None
            try:
                client = get_redis()
                with redis_span("cache.get", cache_key=cache_key):
                    cached = client.get(cache_key)
                if cached is not None:
                    record_cache_event("hits")
                    return deserialize(
                        cached.decode() if isinstance(cached, (bytes, bytearray)) else cached
                    )
                record_cache_event("misses")
            except Exception as exc:  # pragma: no cover
                logger.debug("cache_aside get failed (%s): %s", cache_key, exc)

            started = time.perf_counter()
            value = fn(*args, **kwargs)
            elapsed = time.perf_counter() - started

            if client is not None:
                try:
                    with redis_span("cache.set", cache_key=cache_key):
                        client.set(
                            cache_key,
                            serialize(value),
                            ex=effective_ttl,
                        )
                    record_cache_event("sets")
                    record_timeseries("stats:cache:origin_seconds", elapsed)
                except Exception as exc:  # pragma: no cover
                    logger.debug("cache_aside set failed (%s): %s", cache_key, exc)

            return value

        wrapper.__cache_key_builder__ = lambda *a, **kw: (  # type: ignore[attr-defined]
            key_builder(fn, a, kw) if key_builder else build_cache_key(mod, fn.__name__, a, kw)
        )
        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Async cache-aside decorator
# ---------------------------------------------------------------------------
def async_cache_aside(
    ttl: int | None = None,
    *,
    namespace: str | None = None,
    key_builder: Callable[..., str] | None = None,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Async version of :func:`cache_aside`."""
    from .redis_io import get_async_redis

    effective_ttl = ttl if ttl is not None else get_redis_settings().cache_ttl_seconds

    def decorator(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        mod = namespace or fn.__module__

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            cache_key = (
                key_builder(fn, args, kwargs) if key_builder else
                build_cache_key(mod, fn.__name__, args, kwargs)
            )
            client = None
            try:
                client = get_async_redis()
                with redis_span("cache.get", cache_key=cache_key):
                    cached = await client.get(cache_key)
                if cached is not None:
                    record_cache_event("hits")
                    return json.loads(
                        cached.decode() if isinstance(cached, (bytes, bytearray)) else cached
                    )
                record_cache_event("misses")
            except Exception as exc:  # pragma: no cover
                logger.debug("async_cache_aside get failed (%s): %s", cache_key, exc)

            started = time.perf_counter()
            value = await fn(*args, **kwargs)
            elapsed = time.perf_counter() - started

            if client is not None:
                try:
                    with redis_span("cache.set", cache_key=cache_key):
                        await client.set(
                            cache_key,
                            json.dumps(value, default=str),
                            ex=effective_ttl,
                        )
                    record_cache_event("sets")
                    record_timeseries("stats:cache:origin_seconds", elapsed)
                except Exception as exc:  # pragma: no cover
                    logger.debug("async_cache_aside set failed (%s): %s", cache_key, exc)
                finally:
                    try:
                        await client.close()
                    except Exception:  # pragma: no cover
                        pass

            return value

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Semantic cache
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class SemanticCacheHit:
    prompt: str
    response: Any
    score: float
    metadata: dict[str, Any]


class SemanticCache:
    """Wraps ``redisvl.extensions.llmcache.SemanticCache`` with OTel spans.

    Uses the configured Redis settings and threshold.  When redisvl is
    not installed the wrapper becomes a no-op and every ``check()`` call
    returns ``None`` so downstream code paths follow the cold path.
    """

    def __init__(
        self,
        name: str = "llm_cache",
        *,
        distance_threshold: float | None = None,
        ttl: int | None = None,
        redis_url: str | None = None,
    ) -> None:
        settings = get_redis_settings()
        self.name = name
        self.threshold = (
            distance_threshold if distance_threshold is not None
            else settings.semantic_cache_threshold
        )
        self.ttl = ttl if ttl is not None else settings.cache_ttl_seconds
        self.redis_url = redis_url or settings.dsn()
        self._impl: Any | None = None
        try:
            from redisvl.extensions.llmcache import SemanticCache as _Impl

            self._impl = _Impl(
                name=self.name,
                redis_url=self.redis_url,
                distance_threshold=self.threshold,
                ttl=self.ttl,
            )
        except Exception as exc:  # pragma: no cover - optional dep
            logger.info(
                "redisvl SemanticCache unavailable (%s); using no-op wrapper", exc
            )
            self._impl = None

    @property
    def enabled(self) -> bool:
        return self._impl is not None

    def check(self, prompt: str) -> SemanticCacheHit | None:
        if self._impl is None:
            return None
        with redis_span("semcache.check", cache=self.name):
            results = self._impl.check(prompt=prompt)
        if not results:
            record_cache_event("sem_misses")
            return None
        record_cache_event("sem_hits")
        first = results[0]
        return SemanticCacheHit(
            prompt=first.get("prompt", prompt),
            response=first.get("response"),
            score=float(first.get("vector_distance", 0.0) or 0.0),
            metadata=first.get("metadata") or {},
        )

    def store(self, prompt: str, response: Any, *, metadata: dict[str, Any] | None = None) -> None:
        if self._impl is None:
            return
        with redis_span("semcache.store", cache=self.name):
            self._impl.store(prompt=prompt, response=response, metadata=metadata or {})

    def clear(self) -> None:
        if self._impl is None:
            return
        with redis_span("semcache.clear", cache=self.name):
            try:
                self._impl.clear()
            except Exception as exc:  # pragma: no cover
                logger.debug("SemanticCache clear failed: %s", exc)


# ---------------------------------------------------------------------------
# Invalidation helpers
# ---------------------------------------------------------------------------
class InvalidationHelper:
    """Prefix-based cache invalidation.

    Useful for admin endpoints or post-write hooks where an entire
    namespace should be purged (``DELETE /api/redis/cache/hardware``).
    """

    def __init__(self, client: Any | None = None) -> None:
        self._client = client or get_redis()

    def invalidate_key(self, cache_key: str) -> int:
        with redis_span("cache.del", cache_key=cache_key):
            removed = int(self._client.delete(cache_key))
        if removed:
            record_cache_event("deletes")
        return removed

    def invalidate_prefix(self, prefix: str, *, batch: int = 512) -> int:
        removed = 0
        with redis_span("cache.invalidate_prefix", prefix=prefix):
            for k in self._client.scan_iter(match=f"{prefix}*", count=batch):
                removed += int(self._client.delete(k))
        if removed:
            record_cache_event("deletes")
        return removed


__all__ = [
    "InvalidationHelper",
    "SemanticCache",
    "SemanticCacheHit",
    "async_cache_aside",
    "build_cache_key",
    "cache_aside",
]
