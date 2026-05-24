"""Redis integration service.

Wraps the shared Redis 8 Stack deployment (`base-services/redis/`) with
async-friendly helpers for the management API:

    * connection-pooled async client
    * health check + module guard
    * cached_call / cached_call_async for cache-aside on sync and async
      code paths
    * index_info / stats for the Redis admin endpoints and the Grafana
      dashboard queries

All commands are wrapped in OTel spans so Jaeger/Tempo pick them up.  A
no-op path is kept so the API still runs when Redis is unreachable.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Any, Awaitable, Callable, Iterable, Optional

import httpx  # noqa: F401 - kept for consistency with other services
from opentelemetry import trace
from opentelemetry.trace import SpanKind

from ..config import Settings

logger = logging.getLogger(__name__)
_tracer = trace.get_tracer("rpi.management.redis")


_REQUIRED_MODULES = ("search", "rejson", "timeseries", "bf")


class RedisService:
    """Async service around the shared Redis 8 Stack."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: Any | None = None
        self._client_lock = asyncio.Lock()
        self._instrumented = False

    # ------------------------------------------------------------------ #
    # Connection management
    # ------------------------------------------------------------------ #
    async def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        async with self._client_lock:
            if self._client is None:
                try:
                    import redis.asyncio as aioredis
                except ImportError as exc:
                    raise RuntimeError(
                        "redis>=5.2 is required. Install the management backend's "
                        "pyproject.toml dependencies."
                    ) from exc

                self._client = aioredis.Redis.from_url(
                    self.settings.redis.url,
                    decode_responses=False,
                    socket_timeout=self.settings.redis.health_timeout_seconds,
                    socket_connect_timeout=self.settings.redis.health_timeout_seconds,
                    max_connections=16,
                )

                if not self._instrumented:
                    self._instrument()
                    self._instrumented = True

        return self._client

    def _instrument(self) -> None:
        """Attach the OTel Redis instrumentor.  Safe to call once."""
        try:
            from opentelemetry.instrumentation.redis import RedisInstrumentor

            RedisInstrumentor().instrument()
            logger.info("Redis OTel instrumentation enabled")
        except Exception as exc:  # pragma: no cover
            logger.warning("Redis OTel instrumentation unavailable: %s", exc)

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except Exception as exc:  # pragma: no cover
                logger.warning("Redis close failed: %s", exc)
            self._client = None

    # ------------------------------------------------------------------ #
    # Health + module guard
    # ------------------------------------------------------------------ #
    async def health(self) -> dict[str, Any]:
        """Return a dict with ping status and loaded modules."""
        if not self.settings.redis.enabled:
            return {"enabled": False, "ping": False, "modules": {}}
        with _tracer.start_as_current_span("redis.health", kind=SpanKind.CLIENT) as span:
            try:
                client = await self._get_client()
                pong = await client.ping()
                modules = await self._module_list(client)
                missing = [m for m in _REQUIRED_MODULES if m not in modules]
                span.set_attribute("redis.modules_missing", len(missing))
                return {
                    "enabled": True,
                    "ping": bool(pong),
                    "modules": modules,
                    "missing_modules": missing,
                }
            except Exception as exc:
                span.record_exception(exc)
                logger.warning("Redis health check failed: %s", exc)
                return {"enabled": True, "ping": False, "error": str(exc), "modules": {}}

    async def _module_list(self, client: Any) -> dict[str, str]:
        try:
            rows = await client.execute_command("MODULE", "LIST")
        except Exception:
            return {}
        modules: dict[str, str] = {}
        for row in rows or []:
            info: dict[str, str] = {}
            it = iter(row)
            for k in it:
                v = next(it, None)
                if isinstance(k, (bytes, bytearray)):
                    k = k.decode()
                if isinstance(v, (bytes, bytearray)):
                    v = v.decode()
                info[str(k)] = "" if v is None else str(v)
            name = info.get("name") or info.get("Name") or ""
            ver = info.get("ver") or info.get("version") or ""
            if name:
                modules[name.lower()] = ver
        return modules

    # ------------------------------------------------------------------ #
    # Cache-aside (async + callable over async function)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _cache_key(namespace: str, identifier: str) -> str:
        digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()
        return f"cache:{namespace}:{digest}"

    async def cached_call(
        self,
        namespace: str,
        identifier: str,
        fetch: Callable[[], Awaitable[Any]],
        *,
        ttl: int | None = None,
    ) -> Any:
        """Run ``fetch`` with a Redis cache-aside around it.

        ``identifier`` is a human-readable string uniquely describing the
        call (e.g. ``f"mlflow:experiments:{user}"``).  We hash it to
        produce the actual key so arbitrary identifiers are safe.
        """
        if not self.settings.redis.enabled:
            return await fetch()

        key = self._cache_key(namespace, identifier)
        effective_ttl = ttl if ttl is not None else self.settings.redis.cache_ttl_seconds

        try:
            client = await self._get_client()
        except Exception as exc:  # pragma: no cover
            logger.debug("cached_call cannot reach Redis: %s", exc)
            return await fetch()

        with _tracer.start_as_current_span("redis.cache.get", kind=SpanKind.CLIENT) as span:
            span.set_attribute("cache.key", key)
            try:
                cached = await client.get(key)
            except Exception as exc:
                span.record_exception(exc)
                cached = None

        if cached is not None:
            await self._record_counter("stats:cache", "hits", 1)
            try:
                return json.loads(cached if isinstance(cached, str) else cached.decode())
            except (json.JSONDecodeError, UnicodeDecodeError):
                return cached

        await self._record_counter("stats:cache", "misses", 1)
        started = time.perf_counter()
        value = await fetch()
        elapsed = time.perf_counter() - started

        try:
            payload = json.dumps(value, default=str)
            with _tracer.start_as_current_span("redis.cache.set", kind=SpanKind.CLIENT) as span:
                span.set_attribute("cache.key", key)
                span.set_attribute("cache.ttl", effective_ttl)
                await client.set(key, payload, ex=effective_ttl)
            await self._record_counter("stats:cache", "sets", 1)
        except Exception as exc:  # pragma: no cover
            logger.debug("cached_call set failed: %s", exc)

        await self._record_timeseries("stats:cache:origin_seconds", elapsed)
        return value

    async def invalidate_namespace(self, namespace: str) -> int:
        """Delete every cache-aside key under a namespace. Returns the count."""
        if not self.settings.redis.enabled:
            return 0
        client = await self._get_client()
        removed = 0
        with _tracer.start_as_current_span("redis.cache.invalidate", kind=SpanKind.CLIENT) as span:
            span.set_attribute("cache.namespace", namespace)
            async for key in client.scan_iter(match=f"cache:{namespace}:*", count=512):
                removed += int(await client.delete(key))
            span.set_attribute("cache.invalidated", removed)
        if removed:
            await self._record_counter("stats:cache", "deletes", removed)
        return removed

    # ------------------------------------------------------------------ #
    # Admin helpers (INFO, FT.INFO, stats)
    # ------------------------------------------------------------------ #
    async def server_info(self) -> dict[str, Any]:
        client = await self._get_client()
        with _tracer.start_as_current_span("redis.info", kind=SpanKind.CLIENT):
            raw = await client.execute_command("INFO")
        return _parse_info(raw)

    async def list_indexes(self) -> list[str]:
        client = await self._get_client()
        try:
            with _tracer.start_as_current_span("redis.ft._list", kind=SpanKind.CLIENT):
                rows = await client.execute_command("FT._LIST")
            return [_decode(r) for r in rows or []]
        except Exception:
            return []

    async def index_info(self, index: str) -> dict[str, Any]:
        client = await self._get_client()
        try:
            with _tracer.start_as_current_span("redis.ft.info", kind=SpanKind.CLIENT) as span:
                span.set_attribute("redis.index", index)
                raw = await client.execute_command("FT.INFO", index)
        except Exception:
            return {}
        info: dict[str, Any] = {}
        it = iter(raw)
        for k in it:
            v = next(it, None)
            info[_decode(k)] = _decode(v)
        return info

    async def cache_stats(self) -> dict[str, Any]:
        client = await self._get_client()
        try:
            with _tracer.start_as_current_span("redis.hgetall", kind=SpanKind.CLIENT):
                raw = await client.hgetall("stats:cache")
        except Exception:
            return {}
        return {_decode(k): int(_decode(v) or 0) for k, v in (raw or {}).items()}

    # ------------------------------------------------------------------ #
    # Internal stat helpers
    # ------------------------------------------------------------------ #
    async def _record_counter(self, key: str, field: str, value: int) -> None:
        try:
            client = await self._get_client()
            await client.hincrby(key, field, value)
        except Exception:  # pragma: no cover
            pass

    async def _record_timeseries(self, series: str, value: float) -> None:
        try:
            client = await self._get_client()
            await client.execute_command(
                "TS.ADD", series, "*", value,
                "RETENTION", 7 * 24 * 3600 * 1000,
            )
        except Exception:  # pragma: no cover
            pass

    # ------------------------------------------------------------------ #
    # Raw pipelines helpers exposed for specialized routers
    # ------------------------------------------------------------------ #
    async def execute(self, *args: Any) -> Any:
        client = await self._get_client()
        with _tracer.start_as_current_span(f"redis.{args[0].lower()}", kind=SpanKind.CLIENT):
            return await client.execute_command(*args)

    async def keys_iter(self, pattern: str, count: int = 500):
        client = await self._get_client()
        async for k in client.scan_iter(match=pattern, count=count):
            yield _decode(k)


def _decode(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode()
        except UnicodeDecodeError:
            return value
    return value


def _parse_info(raw: Any) -> dict[str, Any]:
    text = raw.decode() if isinstance(raw, (bytes, bytearray)) else str(raw)
    info: dict[str, Any] = {}
    section = "default"
    for line in text.splitlines():
        if not line:
            continue
        if line.startswith("#"):
            section = line.lstrip("# ").strip().lower() or "default"
            info.setdefault(section, {})
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            info.setdefault(section, {})
            info[section][k.strip()] = v.strip()
    return info


__all__ = ["RedisService"]
