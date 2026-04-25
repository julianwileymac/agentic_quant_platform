"""Small pluggable response caches for Alpha Vantage transports."""
from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class CacheKey:
    function: str
    digest: str

    @classmethod
    def from_params(cls, params: Mapping[str, Any]) -> "CacheKey":
        clean = {k: v for k, v in params.items() if k.lower() != "apikey"}
        payload = json.dumps(clean, sort_keys=True, default=str)
        return cls(
            function=str(clean.get("function") or "UNKNOWN"),
            digest=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        )

    @property
    def value(self) -> str:
        return f"{self.function}:{self.digest}"


class CacheBackend(Protocol):
    def get(self, key: CacheKey) -> Any | None: ...

    def set(self, key: CacheKey, value: Any, ttl_seconds: float) -> None: ...


class NullCache:
    def get(self, key: CacheKey) -> Any | None:  # noqa: ARG002
        return None

    def set(self, key: CacheKey, value: Any, ttl_seconds: float) -> None:  # noqa: ARG002
        return None


class MemoryCache:
    """Process-local TTL cache with bounded insertion order eviction."""

    def __init__(self, *, max_entries: int = 512) -> None:
        self.max_entries = max(1, int(max_entries))
        self._items: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get(self, key: CacheKey) -> Any | None:
        item = self._items.get(key.value)
        if item is None:
            return None
        expires_at, value = item
        if expires_at and expires_at < time.time():
            self._items.pop(key.value, None)
            return None
        self._items.move_to_end(key.value)
        return value

    def set(self, key: CacheKey, value: Any, ttl_seconds: float) -> None:
        if ttl_seconds <= 0:
            return
        self._items[key.value] = (time.time() + ttl_seconds, value)
        self._items.move_to_end(key.value)
        while len(self._items) > self.max_entries:
            self._items.popitem(last=False)


class RedisCache:
    """Minimal Redis cache wrapper accepting sync redis-py clients."""

    def __init__(self, client: Any, *, prefix: str = "aqp:alpha_vantage:cache") -> None:
        self.client = client
        self.prefix = prefix.rstrip(":")

    def _key(self, key: CacheKey) -> str:
        return f"{self.prefix}:{key.value}"

    def get(self, key: CacheKey) -> Any | None:
        raw = self.client.get(self._key(key))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(str(raw))

    def set(self, key: CacheKey, value: Any, ttl_seconds: float) -> None:
        self.client.setex(self._key(key), int(ttl_seconds), json.dumps(value, default=str))


def default_ttl(function: str, params: Mapping[str, Any]) -> float:  # noqa: ARG001
    name = function.upper()
    if name in {"GLOBAL_QUOTE", "CURRENCY_EXCHANGE_RATE", "MARKET_STATUS"}:
        return 15.0
    if "INTRADAY" in name:
        return 60.0
    if name in {"LISTING_STATUS", "OVERVIEW", "ETF_PROFILE"}:
        return 6 * 60 * 60.0
    return 30 * 60.0


def make_cache(
    backend: str,
    *,
    redis_client: Any = None,
    max_entries: int = 512,
    **_: Any,
) -> CacheBackend:
    kind = str(backend or "memory").lower()
    if kind == "redis" and redis_client is not None:
        return RedisCache(redis_client)
    if kind == "none":
        return NullCache()
    return MemoryCache(max_entries=max_entries)


__all__ = [
    "CacheBackend",
    "CacheKey",
    "MemoryCache",
    "NullCache",
    "RedisCache",
    "default_ttl",
    "make_cache",
]
