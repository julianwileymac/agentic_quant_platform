"""Redis 8 Stack client helpers for the pipelines framework.

This module is the single entry point used by `redis_vectors`,
`redis_cache`, `redis_om_models`, `agent_memory`, and pipeline consumers
like Dagster assets and the management-api.  It handles:

    * Connection pooling keyed by DSN (safe for reuse across tasks).
    * OTel span emission for every Redis call (including pipeline
      execution) so traces reach the Jaeger/OTel Collector at
      `otel-collector.observability:4317`.
    * Prometheus counters/histograms compatible with the existing
      `prometheus_client` usage (the backend mounts `/metrics` on the
      FastAPI app so the counters are auto-exposed).
    * A module guard so call sites fail loudly when the connected
      server is missing RediSearch/RedisJSON/etc. (e.g. if someone
      accidentally points at a vanilla Redis or Valkey instance).

The module never imports `redis` at file import time beyond the soft
optional path so pipelines that do not require Redis can still import
this package.
"""

from __future__ import annotations

import functools
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Lock
from typing import TYPE_CHECKING, Any, Callable, Iterable, Iterator

from .config import RedisSettings, get_redis_settings

if TYPE_CHECKING:  # pragma: no cover - import for typing only
    import redis as redis_lib  # noqa: F401

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Optional tracer / metrics helpers (degrade gracefully when deps are missing)
# ---------------------------------------------------------------------------
try:  # pragma: no cover - optional dependency
    from opentelemetry import trace as _otel_trace
    from opentelemetry.trace import SpanKind

    _tracer = _otel_trace.get_tracer("rpi.pipelines.redis")
except Exception:  # pragma: no cover
    _tracer = None  # type: ignore[assignment]
    SpanKind = None  # type: ignore[assignment]


try:  # pragma: no cover - optional dependency
    from prometheus_client import Counter, Histogram

    _REDIS_OPS = Counter(
        "rpi_redis_ops_total",
        "Number of Redis operations executed by the pipelines framework.",
        ["operation", "result"],
    )
    _REDIS_LATENCY = Histogram(
        "rpi_redis_op_seconds",
        "Wall-clock latency of Redis operations executed by the pipelines framework.",
        ["operation"],
        buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
    )
except Exception:  # pragma: no cover

    class _NoopMetric:
        def labels(self, *_, **__) -> "_NoopMetric":
            return self

        def inc(self, *_, **__) -> None:
            return None

        def observe(self, *_, **__) -> None:
            return None

    _REDIS_OPS = _NoopMetric()  # type: ignore[assignment]
    _REDIS_LATENCY = _NoopMetric()  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Pool management
# ---------------------------------------------------------------------------
_pools: dict[str, Any] = {}
_pools_lock = Lock()


@dataclass(slots=True)
class RedisClientBundle:
    """Bundle of sync + helper facades for a configured Redis connection."""

    settings: RedisSettings
    client: Any  # redis.Redis
    pool: Any  # redis.ConnectionPool


def _build_pool(settings: RedisSettings) -> Any:
    try:
        import redis
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "redis-py is required to use pipelines.redis_io. "
            "Install it with `pip install 'redis>=5.2.1'`."
        ) from exc

    return redis.ConnectionPool.from_url(
        settings.dsn(),
        decode_responses=False,
        max_connections=settings.max_connections,
        socket_timeout=settings.socket_timeout,
        socket_connect_timeout=settings.socket_connect_timeout,
    )


def get_redis(settings: RedisSettings | None = None) -> Any:
    """Return a shared, pool-backed sync Redis client.

    Callers should prefer this over instantiating clients directly so the
    framework maintains a single pool per DSN.
    """
    s = settings or get_redis_settings()
    key = s.dsn()

    with _pools_lock:
        pool = _pools.get(key)
        if pool is None:
            pool = _build_pool(s)
            _pools[key] = pool

    import redis

    return redis.Redis(connection_pool=pool)


def get_async_redis(settings: RedisSettings | None = None) -> Any:
    """Return an async Redis client (redis.asyncio.Redis) from the pool URL.

    Note: async Redis uses its own pool namespace; we build it lazily on
    each call because redis.asyncio.ConnectionPool is not safe to share
    across event loops without care.
    """
    s = settings or get_redis_settings()
    try:
        import redis.asyncio as aioredis
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("redis>=5.2 with asyncio support is required") from exc

    return aioredis.Redis.from_url(
        s.dsn(),
        decode_responses=False,
        max_connections=s.max_connections,
        socket_timeout=s.socket_timeout,
        socket_connect_timeout=s.socket_connect_timeout,
    )


def client_bundle(settings: RedisSettings | None = None) -> RedisClientBundle:
    """Return a RedisClientBundle (settings + client + pool)."""
    s = settings or get_redis_settings()
    client = get_redis(s)
    return RedisClientBundle(settings=s, client=client, pool=client.connection_pool)


# ---------------------------------------------------------------------------
# Observability helpers
# ---------------------------------------------------------------------------
@contextmanager
def redis_span(operation: str, **attributes: Any) -> Iterator[None]:
    """Context manager emitting an OTel span + Prometheus metrics.

    Wrap Redis calls you want traced::

        with redis_span("ft.search", index="idx:chunks"):
            client.ft("idx:chunks").search(...)
    """
    started = time.perf_counter()
    span_cm = None
    if _tracer is not None and SpanKind is not None:
        span_cm = _tracer.start_as_current_span(
            f"redis.{operation}", kind=SpanKind.CLIENT
        )
        span = span_cm.__enter__()  # type: ignore[union-attr]
        try:
            span.set_attribute("db.system", "redis")
            span.set_attribute("db.operation", operation)
            for k, v in attributes.items():
                span.set_attribute(f"redis.{k}", str(v))
        except Exception:  # pragma: no cover
            pass

    result = "ok"
    try:
        yield
    except Exception:
        result = "error"
        raise
    finally:
        elapsed = time.perf_counter() - started
        try:
            _REDIS_OPS.labels(operation=operation, result=result).inc()
            _REDIS_LATENCY.labels(operation=operation).observe(elapsed)
        except Exception:  # pragma: no cover
            pass
        if span_cm is not None:
            try:
                span_cm.__exit__(None, None, None)
            except Exception:  # pragma: no cover
                pass


def traced(operation: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that wraps a sync function in a redis_span."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with redis_span(operation):
                return fn(*args, **kwargs)

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Keyspace helpers
# ---------------------------------------------------------------------------
def key(*parts: str | int, prefix: str | None = None) -> str:
    """Construct a namespaced Redis key.

    ``prefix`` defaults to ``RedisSettings.index_prefix`` which is itself
    controlled by the ``REDIS_INDEX_PREFIX`` env var.  This keeps every
    subsystem's keys under a single configurable root so multi-tenant
    dev/prod clusters can coexist.
    """
    stem = prefix if prefix is not None else get_redis_settings().index_prefix
    joined = ":".join(str(p).strip(":") for p in parts if str(p))
    return f"{stem}:{joined}" if stem else joined


def scan_iter(pattern: str, *, count: int = 500, client: Any | None = None) -> Iterator[bytes]:
    """Yield every key matching *pattern* without blocking Redis."""
    client = client or get_redis()
    with redis_span("scan", pattern=pattern):
        yield from client.scan_iter(match=pattern, count=count)


def delete_matching(pattern: str, *, client: Any | None = None) -> int:
    """Delete every key matching *pattern* and return the count removed."""
    client = client or get_redis()
    deleted = 0
    with redis_span("delete_matching", pattern=pattern):
        for batch in _batched(scan_iter(pattern, client=client), 256):
            if batch:
                deleted += int(client.delete(*batch))
    return deleted


def _batched(iterable: Iterable[Any], size: int) -> Iterator[list[Any]]:
    batch: list[Any] = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


# ---------------------------------------------------------------------------
# Health / module guards
# ---------------------------------------------------------------------------
def ping(client: Any | None = None) -> bool:
    client = client or get_redis()
    try:
        with redis_span("ping"):
            return bool(client.ping())
    except Exception as exc:  # pragma: no cover
        logger.warning("Redis ping failed: %s", exc)
        return False


def loaded_modules(client: Any | None = None) -> dict[str, str]:
    """Return a mapping of loaded module name -> version string.

    Uses `MODULE LIST` which is available in both Redis OSS 8 and Redis
    Stack.  Names are lower-cased so comparisons are stable.
    """
    client = client or get_redis()
    with redis_span("module_list"):
        rows = client.execute_command("MODULE", "LIST")
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


_REQUIRED_MODULES_DEFAULT = ("search", "rejson", "timeseries", "bf")


def require_modules(
    names: Iterable[str] = _REQUIRED_MODULES_DEFAULT,
    *,
    client: Any | None = None,
) -> None:
    """Raise if the configured Redis does not have *all* requested modules.

    Redis 8 OSS and Redis Stack both publish module names:
        - ``search``    (RediSearch)
        - ``rejson``    (RedisJSON, sometimes reported as ``ReJSON``)
        - ``timeseries``
        - ``bf``        (RedisBloom)
    """
    modules = loaded_modules(client=client)
    missing = [n for n in names if n.lower() not in modules]
    if missing:
        raise RuntimeError(
            "Redis is missing required modules: "
            + ", ".join(missing)
            + f". Loaded: {sorted(modules.keys())}. "
            "Deploy Redis 8 Stack (see kubernetes/base-services/redis/) or "
            "enable the listed modules on the target instance."
        )


# ---------------------------------------------------------------------------
# Stats helpers (backed by Redis structures; surfaces in the Grafana panels)
# ---------------------------------------------------------------------------
def record_cache_event(kind: str, *, client: Any | None = None) -> None:
    """Increment a counter in the ``stats:cache`` hash (used by dashboards).

    ``kind`` should be one of ``hits``, ``misses``, ``sets``, ``deletes``.
    """
    client = client or get_redis()
    try:
        with redis_span("hincrby", key="stats:cache", field=kind):
            client.hincrby("stats:cache", kind, 1)
    except Exception:  # pragma: no cover
        logger.debug("record_cache_event failed for %s", kind)


def record_timeseries(
    series: str,
    value: float,
    *,
    labels: dict[str, str] | None = None,
    client: Any | None = None,
    retention_ms: int = 7 * 24 * 3600 * 1000,
) -> None:
    """Append a value to a RedisTimeSeries, creating the series if needed.

    Used by examples and the document-store counters to feed the Grafana
    Redis data-source `TS.RANGE` panels.
    """
    client = client or get_redis()
    try:
        with redis_span("ts.add", series=series):
            args: list[Any] = [
                "TS.ADD", series, "*", value,
                "RETENTION", retention_ms,
                "LABELS",
            ]
            for k, v in (labels or {}).items():
                args.extend([k, v])
            client.execute_command(*args)
    except Exception as exc:  # pragma: no cover
        logger.debug("record_timeseries failed for %s: %s", series, exc)


__all__ = [
    "RedisClientBundle",
    "client_bundle",
    "delete_matching",
    "get_async_redis",
    "get_redis",
    "key",
    "loaded_modules",
    "ping",
    "record_cache_event",
    "record_timeseries",
    "redis_span",
    "require_modules",
    "scan_iter",
    "traced",
]
