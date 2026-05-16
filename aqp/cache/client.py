"""Redis client wrapper with an in-memory fallback for the metadata cache.

Mirrors the ``RedisVectorStore`` fallback pattern from
:mod:`aqp.rag.redis_store` so the platform never hard-fails when Redis
isn't reachable. Unit tests and the local dev loop run entirely against
the in-memory backend.

Client is configured from :attr:`aqp.config.settings.Settings.cache_redis_url`
(empty falls back to :attr:`Settings.redis_url`) on a separate logical
DB (:attr:`Settings.cache_redis_db`, default 2) so the cache cannot
collide with RAG vector indexes (:attr:`Settings.rag_redis_prefix`),
the pub/sub bus (:attr:`Settings.redis_pubsub_url`), or the kill-switch
(:attr:`Settings.risk_kill_switch_key`).
"""
from __future__ import annotations

import json
import logging
import random
import re
import threading
from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from functools import lru_cache
from typing import Any

from aqp.config import settings

logger = logging.getLogger(__name__)


# --------------------------------------------------------------- helpers


def jitter_ttl(base_ttl: int, *, pct: int | None = None) -> int:
    """Spread expirations so simultaneous-write batches don't expire as a wave.

    Returns ``base_ttl + random(0, base_ttl * pct/100)`` rounded to whole
    seconds. ``pct`` defaults to :attr:`Settings.cache_ttl_jitter_pct`
    (10% out of the box) so prefetch + write-through share a single
    knob. Floor at 60 seconds so the in-memory backend never sees a
    nonsense zero TTL.
    """
    base = max(60, int(base_ttl))
    if pct is None:
        pct = int(getattr(settings, "cache_ttl_jitter_pct", 10) or 0)
    pct = max(0, min(50, int(pct)))
    if pct == 0:
        return base
    return base + int(random.random() * base * pct / 100.0)


# --------------------------------------------------------------- in-memory fallback


class _MemoryBackend:
    """Process-local fallback for ``ZRANGEBYLEX`` / ``HSET`` / ``HGET``.

    Intentionally simple — no eviction, no TTL, no clustering. The real
    Redis backend is tested in CI; this fallback exists so unit tests
    that only touch business logic (not infrastructure) run without a
    server.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._zsets: dict[str, dict[str, float]] = {}
        self._hashes: dict[str, dict[str, str]] = {}
        self._strings: dict[str, str] = {}

    # ---- sorted sets ----
    def zadd(self, key: str, mapping: Mapping[str, float]) -> int:
        with self._lock:
            bucket = self._zsets.setdefault(key, {})
            n = 0
            for member, score in mapping.items():
                if member not in bucket:
                    n += 1
                bucket[member] = float(score)
            return n

    def zrem(self, key: str, *members: str) -> int:
        with self._lock:
            bucket = self._zsets.get(key) or {}
            n = 0
            for m in members:
                if m in bucket:
                    bucket.pop(m, None)
                    n += 1
            return n

    def zrange_lex(
        self,
        key: str,
        *,
        prefix: str,
        offset: int,
        count: int,
    ) -> list[str]:
        with self._lock:
            bucket = self._zsets.get(key) or {}
            members = sorted(
                m for m in bucket if m.lower().startswith(prefix.lower())
            )
            if offset:
                members = members[offset:]
            if count and count > 0:
                members = members[:count]
            return members

    def zcard(self, key: str) -> int:
        with self._lock:
            return len(self._zsets.get(key) or {})

    # ---- hashes ----
    def hset(self, key: str, mapping: Mapping[str, str]) -> int:
        with self._lock:
            bucket = self._hashes.setdefault(key, {})
            n = 0
            for k, v in mapping.items():
                if k not in bucket:
                    n += 1
                bucket[k] = str(v)
            return n

    def hgetall(self, key: str) -> dict[str, str]:
        with self._lock:
            return dict(self._hashes.get(key) or {})

    def hget(self, key: str, field: str) -> str | None:
        with self._lock:
            return (self._hashes.get(key) or {}).get(field)

    def hdel(self, key: str, *fields: str) -> int:
        with self._lock:
            bucket = self._hashes.get(key) or {}
            n = 0
            for f in fields:
                if f in bucket:
                    bucket.pop(f, None)
                    n += 1
            return n

    # ---- strings ----
    def set(self, key: str, value: str) -> None:
        with self._lock:
            self._strings[key] = value

    def get(self, key: str) -> str | None:
        with self._lock:
            return self._strings.get(key)

    def expire(self, key: str, _ttl: int) -> None:
        # No-op: the in-memory backend has no TTL semantics.
        return

    def delete(self, *keys: str) -> int:
        with self._lock:
            n = 0
            for k in keys:
                if k in self._zsets:
                    self._zsets.pop(k, None)
                    n += 1
                if k in self._hashes:
                    self._hashes.pop(k, None)
                    n += 1
                if k in self._strings:
                    self._strings.pop(k, None)
                    n += 1
            return n

    def keys(self, pattern: str) -> list[str]:
        with self._lock:
            regex = _glob_to_regex(pattern)
            out: list[str] = []
            for collection in (self._zsets, self._hashes, self._strings):
                for key in collection:
                    if regex.match(key):
                        out.append(key)
            return sorted(set(out))


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a Redis glob into a python regex (``*`` and ``?`` only)."""
    parts: list[str] = []
    for ch in pattern:
        if ch == "*":
            parts.append(".*")
        elif ch == "?":
            parts.append(".")
        else:
            parts.append(re.escape(ch))
    return re.compile("^" + "".join(parts) + "$")


# --------------------------------------------------------------- client


class _L1Cache:
    """Per-process tiny TTL cache in front of the L2 Redis client.

    Sub-100ns gets at the cost of accepting up to
    :attr:`Settings.cache_l1_ttl_s` of staleness across worker
    processes. Disabled when ``cache_l1_enabled=False`` so production
    deploys with tight consistency requirements can opt out.
    """

    def __init__(
        self,
        *,
        max_entries: int,
        ttl_seconds: int,
    ) -> None:
        from collections import OrderedDict

        self._lock = threading.RLock()
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._max = max(64, int(max_entries))
        self._ttl = max(1, int(ttl_seconds))

    def get(self, key: str) -> tuple[bool, Any]:
        import time

        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return False, None
            expires_at, value = entry
            if time.time() >= expires_at:
                self._cache.pop(key, None)
                return False, None
            # LRU bookkeeping — move to end.
            self._cache.move_to_end(key)
            return True, value

    def set(self, key: str, value: Any) -> None:
        import time

        with self._lock:
            self._cache[key] = (time.time() + self._ttl, value)
            self._cache.move_to_end(key)
            while len(self._cache) > self._max:
                self._cache.popitem(last=False)

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


class MetadataCache:
    """High-level cache client used by routes, services, and the prefetcher.

    All keys are namespaced under :attr:`Settings.cache_key_prefix`.
    The class is intentionally narrow: callers should never reach for
    ``self._client`` directly; if a needed verb is missing, add it
    here.

    Three layers:

    1. **L1** — in-process LRU TTL (5s default). Sub-100ns hits.
    2. **L2** — Redis (or the in-memory fallback). Sub-millisecond hits.
    3. **Postgres** — the canonical source the prefetcher pulls from.

    Reads check L1 before L2; writes invalidate L1 on the affected
    keys. Single-flight locks coalesce concurrent cold L2 reads on the
    same key.
    """

    def __init__(
        self,
        *,
        url: str | None = None,
        db: int | None = None,
    ) -> None:
        self.url = url or self._resolved_url()
        self.db = int(db if db is not None else settings.cache_redis_db)
        self._lock = threading.RLock()
        self._client: Any | None = self._make_client()
        self._memory: _MemoryBackend | None = (
            None if self._client is not None else _MemoryBackend()
        )
        self._l1: _L1Cache | None = (
            _L1Cache(
                max_entries=int(getattr(settings, "cache_l1_max_entries", 2048) or 2048),
                ttl_seconds=int(getattr(settings, "cache_l1_ttl_s", 5) or 5),
            )
            if bool(getattr(settings, "cache_l1_enabled", True))
            else None
        )
        self._single_flight_locks: dict[str, threading.Lock] = {}
        self._sf_lock = threading.Lock()

    # ------------------------------------------------- bootstrap helpers
    @staticmethod
    def _resolved_url() -> str:
        configured = (settings.cache_redis_url or "").strip()
        return configured or settings.redis_url

    def _make_client(self) -> Any | None:
        if not settings.cache_enabled:
            logger.info("metadata cache disabled via settings.cache_enabled")
            return None
        try:
            import redis  # type: ignore[import-not-found]
        except Exception:  # pragma: no cover - redis-py optional
            logger.warning(
                "redis-py not installed; metadata cache using in-memory fallback"
            )
            return None
        try:
            client = redis.Redis.from_url(
                self.url,
                db=self.db,
                decode_responses=True,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
            )
            client.ping()
            return client
        except Exception:  # noqa: BLE001
            logger.warning(
                "metadata cache redis at %s db=%s unreachable; using in-memory fallback",
                self.url,
                self.db,
            )
            return None

    @property
    def is_remote(self) -> bool:
        return self._client is not None

    # ------------------------------------------------- sorted-set verbs
    def zadd(self, key: str, mapping: Mapping[str, float]) -> int:
        if not mapping:
            return 0
        self._invalidate_l1_for(key)
        if self._client is not None:
            return int(self._client.zadd(key, dict(mapping)))
        assert self._memory is not None
        return self._memory.zadd(key, mapping)

    def zrem(self, key: str, *members: str) -> int:
        if not members:
            return 0
        self._invalidate_l1_for(key)
        if self._client is not None:
            return int(self._client.zrem(key, *members))
        assert self._memory is not None
        return self._memory.zrem(key, *members)

    def zcard(self, key: str) -> int:
        if self._client is not None:
            return int(self._client.zcard(key))
        assert self._memory is not None
        return self._memory.zcard(key)

    def zrange_lex(
        self,
        key: str,
        *,
        prefix: str = "",
        offset: int = 0,
        count: int = 100,
    ) -> list[str]:
        """Return up to ``count`` members whose lowercased value starts with ``prefix``.

        Uses ``ZRANGEBYLEX`` on Redis (sub-millisecond) and falls back
        to a Python sort on the in-memory backend. Members are stored
        verbatim (case preserved) but matched case-insensitively.

        L1 + single-flight: identical concurrent reads on the same
        ``(key, prefix, offset, count)`` deduplicate into a single L2
        call and the result is briefly cached for sub-second
        re-renders of the same dropdown.
        """
        l1_key = f"zlex|{key}|{prefix}|{offset}|{count}"
        if self._l1 is not None:
            hit, cached = self._l1.get(l1_key)
            if hit:
                return list(cached)

        def _fetch() -> list[str]:
            if self._client is not None:
                min_token = f"[{prefix.lower()}" if prefix else "-"
                max_token = f"[{prefix.lower()}\xff" if prefix else "+"
                try:
                    raw = self._client.zrangebylex(
                        key,
                        min_token,
                        max_token,
                        start=offset,
                        num=count,
                    )
                except Exception:  # noqa: BLE001
                    # ZRANGEBYLEX requires equal scores; if scoring drifted,
                    # fall back to ZRANGE with a python filter.
                    raw = self._client.zrange(key, 0, -1)
                    lower = prefix.lower()
                    if lower:
                        raw = [m for m in raw if str(m).lower().startswith(lower)]
                    raw = raw[offset : offset + count] if count > 0 else raw[offset:]
                return [str(m) for m in raw]
            assert self._memory is not None
            return self._memory.zrange_lex(
                key, prefix=prefix, offset=offset, count=count
            )

        result = self._single_flight(l1_key, _fetch)
        if self._l1 is not None:
            self._l1.set(l1_key, list(result))
        return result

    # ------------------------------------------------- single-flight
    def _single_flight(self, key: str, fn: Any) -> Any:
        """Coalesce concurrent fetches on the same logical key.

        Without single-flight, a cold dropdown loaded from 10 browser
        tabs would issue 10 identical Postgres queries. With it, the
        first call holds the lock + fetches; siblings block, then
        observe the cached value the first call writes back. Disabled
        by setting ``cache_single_flight_enabled=False``.
        """
        if not bool(getattr(settings, "cache_single_flight_enabled", True)):
            return fn()
        with self._sf_lock:
            lock = self._single_flight_locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._single_flight_locks[key] = lock
        with lock:
            # L1 may have been populated by the previous holder; re-check.
            if self._l1 is not None:
                hit, cached = self._l1.get(key)
                if hit:
                    return cached
            try:
                return fn()
            finally:
                # Drop the lock object so it can be GC'd; concurrent
                # callers grab a fresh lock on the next attempt.
                with self._sf_lock:
                    self._single_flight_locks.pop(key, None)

    # ------------------------------------------------- hash verbs
    def hset(self, key: str, mapping: Mapping[str, Any]) -> int:
        normalised = {k: _stringify(v) for k, v in mapping.items()}
        if not normalised:
            return 0
        # Invalidate any L1 entry derived from this key so the next
        # read goes through to Redis. Cheap: L1 is a small dict.
        self._invalidate_l1_for(key)
        if self._client is not None:
            return int(self._client.hset(key, mapping=normalised))
        assert self._memory is not None
        return self._memory.hset(key, normalised)

    def hgetall(self, key: str) -> dict[str, Any]:
        l1_key = f"hgetall|{key}"
        if self._l1 is not None:
            hit, cached = self._l1.get(l1_key)
            if hit:
                return dict(cached)

        def _fetch() -> dict[str, Any]:
            if self._client is not None:
                raw = self._client.hgetall(key) or {}
            else:
                assert self._memory is not None
                raw = self._memory.hgetall(key)
            return {str(k): _maybe_parse_json(v) for k, v in raw.items()}

        result = self._single_flight(l1_key, _fetch)
        if self._l1 is not None:
            self._l1.set(l1_key, dict(result))
        return result

    def hdel(self, key: str, *fields: str) -> int:
        if not fields:
            return 0
        self._invalidate_l1_for(key)
        if self._client is not None:
            return int(self._client.hdel(key, *fields))
        assert self._memory is not None
        return self._memory.hdel(key, *fields)

    def _invalidate_l1_for(self, key: str) -> None:
        """Drop every L1 entry derived from *key*.

        L1 keys all encode the underlying Redis key as a suffix
        (``zlex|<key>|...``, ``hgetall|<key>``). Walking the small L1
        dict is cheap; this keeps the multi-tier consistency simple
        without trying to track exact dependency edges.
        """
        if self._l1 is None:
            return
        # Iterate over a snapshot since invalidate mutates.
        try:
            with self._l1._lock:  # noqa: SLF001 - intentional internal access
                keys = [k for k in self._l1._cache if key in k]  # noqa: SLF001
            for k in keys:
                self._l1.invalidate(k)
        except Exception:  # noqa: BLE001
            # Worst case the L1 keeps a stale entry until its TTL
            # expires; that's the documented consistency window.
            return

    # ------------------------------------------------- key admin
    def expire(self, key: str, ttl_seconds: int, *, jitter: bool = True) -> None:
        """Set a TTL on *key*.

        By default applies :func:`jitter_ttl` so simultaneous-write
        batches don't expire on the same second. Pass ``jitter=False``
        when the caller has already pre-jittered the value or wants a
        hard, predictable expiration (e.g. lock keys).
        """
        if ttl_seconds <= 0:
            return
        actual = jitter_ttl(int(ttl_seconds)) if jitter else int(ttl_seconds)
        if self._client is not None:
            self._client.expire(key, actual)
            return
        assert self._memory is not None
        self._memory.expire(key, actual)

    def set_string(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        if self._client is not None:
            if ttl_seconds and ttl_seconds > 0:
                self._client.set(key, value, ex=int(ttl_seconds))
            else:
                self._client.set(key, value)
            return
        assert self._memory is not None
        self._memory.set(key, value)

    def get_string(self, key: str) -> str | None:
        if self._client is not None:
            value = self._client.get(key)
            return None if value is None else str(value)
        assert self._memory is not None
        return self._memory.get(key)

    def delete(self, *keys: str) -> int:
        if not keys:
            return 0
        for k in keys:
            self._invalidate_l1_for(k)
        if self._client is not None:
            return int(self._client.delete(*keys))
        assert self._memory is not None
        return self._memory.delete(*keys)

    def keys(self, pattern: str) -> list[str]:
        if self._client is not None:
            try:
                return [str(k) for k in self._client.keys(pattern)]
            except Exception:  # noqa: BLE001
                return []
        assert self._memory is not None
        return self._memory.keys(pattern)

    # ------------------------------------------------- pipeline support
    @contextmanager
    def pipeline(self):
        """Context manager producing a Redis pipeline (or a no-op shim)."""
        if self._client is not None:
            pipe = self._client.pipeline(transaction=False)
            try:
                yield pipe
                pipe.execute()
            finally:
                pipe.reset()
            return
        # In-memory pipelines are just sequential calls.
        yield _MemoryPipeline(self)

    @staticmethod
    def stringify_mapping(mapping: Mapping[str, Any]) -> dict[str, str]:
        """Normalise a mapping into the str/str shape Redis HSET requires.

        Use this before passing a payload to ``pipe.hset`` inside a
        ``with cache.pipeline() as pipe:`` block — the raw Redis
        pipeline's hset doesn't route through :meth:`MetadataCache.hset`
        and will reject dict / list values.
        """
        return {str(k): _stringify(v) for k, v in mapping.items()}

    def info(self) -> dict[str, Any]:
        return {
            "remote": self.is_remote,
            "url": self.url if self.is_remote else None,
            "db": self.db if self.is_remote else None,
            "fallback": "in-memory" if not self.is_remote else None,
            "prefix": settings.cache_key_prefix,
        }


class _MemoryPipeline:
    """Tiny shim so callers can use ``with cache.pipeline() as pipe`` uniformly.

    Mirrors enough of redis-py's pipeline surface that the prefetcher can
    call ``pipe.hset(key, mapping=...)`` / ``pipe.zadd(key, {name: score})``
    interchangeably with the real client.
    """

    def __init__(self, cache: MetadataCache) -> None:
        self._cache = cache

    def zadd(self, key: str, mapping: Mapping[str, float], *_args: Any, **_kwargs: Any) -> int:
        return self._cache.zadd(key, mapping)

    def hset(
        self,
        key: str,
        field: Any = None,
        value: Any = None,
        mapping: Mapping[str, Any] | None = None,
        items: Any = None,  # noqa: ARG002 — redis-py compat
    ) -> int:
        if mapping is not None:
            return self._cache.hset(key, mapping)
        if field is None:
            return 0
        if isinstance(field, Mapping):
            return self._cache.hset(key, field)
        return self._cache.hset(key, {str(field): value})

    def set(self, key: str, value: Any, *_args: Any, **_kwargs: Any) -> None:
        self._cache.set_string(key, _stringify(value))

    def expire(self, key: str, ttl_seconds: int, *_args: Any, **_kwargs: Any) -> None:
        self._cache.expire(key, ttl_seconds)

    def delete(self, *keys: str) -> int:
        return self._cache.delete(*keys)

    def execute(self) -> None:
        return None


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if value is None:
        return ""
    try:
        return json.dumps(value, default=str, sort_keys=True)
    except Exception:  # noqa: BLE001
        return str(value)


def _maybe_parse_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped:
        return value
    if stripped[0] in "{[" and stripped[-1] in "}]":
        try:
            return json.loads(stripped)
        except Exception:  # noqa: BLE001
            return value
    return value


@lru_cache(maxsize=1)
def get_cache() -> MetadataCache:
    """Process-wide cached :class:`MetadataCache`."""
    return MetadataCache()


def reset_cache_singleton() -> None:
    """Test helper: drop the cached singleton (next ``get_cache`` rebuilds)."""
    get_cache.cache_clear()


def cache_iter_categories(cache: MetadataCache, categories: Iterable[str]) -> dict[str, int]:
    """Diagnostic helper: how many members each category has cached."""
    from aqp.cache.keys import CACHE_CATEGORIES, names_zset

    out: dict[str, int] = {}
    for category in categories:
        if category not in CACHE_CATEGORIES:
            continue
        out[category] = cache.zcard(names_zset(category))
    return out


__all__ = [
    "MetadataCache",
    "cache_iter_categories",
    "get_cache",
    "jitter_ttl",
    "reset_cache_singleton",
]
