"""Cache-aware sync and async Alpha Vantage transports."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import random
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from functools import lru_cache
from typing import Any

import httpx

from aqp.config import settings
from aqp.data.sources.alpha_vantage._cache import CacheBackend, CacheKey, NullCache, default_ttl
from aqp.data.sources.alpha_vantage._errors import (
    AlphaVantagePayloadError,
    RateLimitError,
    RateLimitKind,
    TransientError,
    classify_payload,
)
from aqp.data.sources.alpha_vantage._rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

_DISTRIBUTED_LIMIT_SCRIPT = """
local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, 0, now_ms - window_ms)
local count = redis.call('ZCARD', key)
if count < limit then
  redis.call('ZADD', key, now_ms, member)
  redis.call('PEXPIRE', key, window_ms * 2)
  return 0
end
local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
if oldest[2] == nil then
  return 1000
end
return math.max(1, (tonumber(oldest[2]) + window_ms) - now_ms)
"""


@lru_cache(maxsize=4)
def _redis_client(url: str) -> Any:
    import redis

    return redis.Redis.from_url(url)


def _distributed_window_acquire(
    *,
    api_key: str,
    suffix: str,
    window_ms: int,
    limit: int,
) -> None:
    """Best-effort Redis-backed sliding-window throttle."""
    url = str(settings.redis_url or "").strip()
    if not url or limit <= 0:
        return
    key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
    key = f"aqp:alpha_vantage:rate:{suffix}:{key_hash}"
    client = _redis_client(url)
    while True:
        now_ms = int(time.time() * 1000)
        wait_ms = int(
            client.eval(
                _DISTRIBUTED_LIMIT_SCRIPT,
                1,
                key,
                now_ms,
                int(window_ms),
                int(limit),
                f"{now_ms}:{uuid.uuid4().hex}",
            )
        )
        if wait_ms <= 0:
            return
        time.sleep(max(0.01, wait_ms / 1000.0))


def _distributed_acquire(api_key: str, rpm: int) -> None:
    """Throttle shared Alpha Vantage API-key usage across workers/processes."""
    _distributed_window_acquire(api_key=api_key, suffix="minute", window_ms=60_000, limit=rpm)
    _distributed_window_acquire(
        api_key=api_key,
        suffix="second",
        window_ms=1_000,
        limit=max(1, int(settings.alpha_vantage_rps_limit)),
    )


async def _adistributed_acquire(api_key: str, rpm: int) -> None:
    await asyncio.to_thread(_distributed_acquire, api_key, rpm)


@dataclass
class TransportConfig:
    base_url: str = "https://www.alphavantage.co/query"
    timeout_seconds: float = 15.0
    max_retries: int = 5
    backoff_base: float = 1.0
    backoff_cap: float = 60.0
    headers: Mapping[str, str] = field(default_factory=dict)
    user_agent: str = "aqp-alpha-vantage-client/0.1"
    trust_env: bool = True
    rapidapi: bool = False
    rapidapi_host: str = "alpha-vantage.p.rapidapi.com"


class _TransportMixin:
    api_key: str
    config: TransportConfig
    rate_limiter: RateLimiter
    cache: CacheBackend

    def _build_headers(self) -> dict[str, str]:
        headers = {"User-Agent": self.config.user_agent, **dict(self.config.headers)}
        if self.config.rapidapi:
            headers.setdefault("x-rapidapi-host", self.config.rapidapi_host)
            headers.setdefault("x-rapidapi-key", self.api_key)
        return headers

    def _prepare_params(self, params: Mapping[str, Any], *, datatype: str | None = None) -> dict[str, Any]:
        query = {k: v for k, v in params.items() if v is not None and v != ""}
        if not self.config.rapidapi:
            query["apikey"] = self.api_key
        if datatype and "datatype" not in query:
            query["datatype"] = datatype
        return query

    def _process_response(self, response: httpx.Response, *, datatype: str | None) -> tuple[Any, Exception | None]:
        if response.status_code in (500, 502, 503, 504, 522, 524):
            return None, TransientError(f"Alpha Vantage HTTP {response.status_code}")
        if response.status_code == 429:
            return None, RateLimitError(
                "HTTP 429 Too Many Requests",
                kind=RateLimitKind.RPM,
                retry_after_seconds=_parse_retry_after(response.headers),
            )
        if response.status_code >= 400:
            return None, AlphaVantagePayloadError(
                f"Alpha Vantage HTTP {response.status_code}: {response.text[:200]}",
            )
        if datatype == "csv":
            return response.text, None
        try:
            payload = response.json()
        except ValueError:
            return None, AlphaVantagePayloadError("Alpha Vantage returned invalid JSON")
        return payload, classify_payload(payload)

    def _sleep_seconds(self, attempt: int, hint: float | None = None) -> float:
        if hint is not None:
            return max(0.0, hint)
        base = min(self.config.backoff_cap, self.config.backoff_base * (2 ** max(attempt - 1, 0)))
        return base + random.uniform(0.0, min(base, 1.0))


class Transport(_TransportMixin):
    """Synchronous Alpha Vantage transport."""

    def __init__(
        self,
        api_key: str,
        *,
        rate_limiter: RateLimiter | None = None,
        cache: CacheBackend | None = None,
        config: TransportConfig | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.config = config or TransportConfig()
        self.rate_limiter = rate_limiter or RateLimiter()
        self.cache = cache or NullCache()
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=self.config.timeout_seconds,
            headers=self._build_headers(),
            trust_env=self.config.trust_env,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def request(
        self,
        params: Mapping[str, Any],
        *,
        cache: bool = True,
        cache_ttl: float | None = None,
        datatype: str | None = None,
    ) -> Any:
        query = self._prepare_params(params, datatype=datatype)
        response_datatype = datatype or str(query.get("datatype") or "").lower() or None
        key = CacheKey.from_params(query)
        ttl = cache_ttl if cache_ttl is not None else default_ttl(key.function, query)
        if cache and ttl > 0:
            hit = self.cache.get(key)
            if hit is not None:
                return hit
        payload = self._retry_request(query, datatype=response_datatype)
        if cache and ttl > 0 and response_datatype != "csv":
            self.cache.set(key, payload, ttl)
        return payload

    def _retry_request(self, query: Mapping[str, Any], *, datatype: str | None) -> Any:
        last_exc: Exception | None = None
        for attempt in range(1, self.config.max_retries + 2):
            try:
                _distributed_acquire(self.api_key, self.rate_limiter.rpm)
            except Exception:
                logger.debug("distributed Alpha Vantage limiter unavailable", exc_info=True)
            self.rate_limiter.acquire()
            try:
                response = self._client.get(self.config.base_url, params=query)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = TransientError(f"Transport error: {exc}")
                _sleep_sync(self._sleep_seconds(attempt))
                continue
            payload, err = self._process_response(response, datatype=datatype)
            if err is None:
                return payload
            if isinstance(err, RateLimitError) and err.kind == RateLimitKind.RPM:
                last_exc = err
                _sleep_sync(self._sleep_seconds(attempt, err.retry_after_seconds))
                continue
            if isinstance(err, TransientError):
                last_exc = err
                _sleep_sync(self._sleep_seconds(attempt))
                continue
            raise err
        raise last_exc or TransientError("Unknown Alpha Vantage transport failure")


class AsyncTransport(_TransportMixin):
    """Asynchronous Alpha Vantage transport."""

    def __init__(
        self,
        api_key: str,
        *,
        rate_limiter: RateLimiter | None = None,
        cache: CacheBackend | None = None,
        config: TransportConfig | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.config = config or TransportConfig()
        self.rate_limiter = rate_limiter or RateLimiter()
        self.cache = cache or NullCache()
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=self.config.timeout_seconds,
            headers=self._build_headers(),
            trust_env=self.config.trust_env,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def request(
        self,
        params: Mapping[str, Any],
        *,
        cache: bool = True,
        cache_ttl: float | None = None,
        datatype: str | None = None,
    ) -> Any:
        query = self._prepare_params(params, datatype=datatype)
        response_datatype = datatype or str(query.get("datatype") or "").lower() or None
        key = CacheKey.from_params(query)
        ttl = cache_ttl if cache_ttl is not None else default_ttl(key.function, query)
        if cache and ttl > 0:
            hit = self.cache.get(key)
            if hit is not None:
                return hit
        payload = await self._retry_request(query, datatype=response_datatype)
        if cache and ttl > 0 and response_datatype != "csv":
            self.cache.set(key, payload, ttl)
        return payload

    async def _retry_request(self, query: Mapping[str, Any], *, datatype: str | None) -> Any:
        last_exc: Exception | None = None
        for attempt in range(1, self.config.max_retries + 2):
            try:
                await _adistributed_acquire(self.api_key, self.rate_limiter.rpm)
            except Exception:
                logger.debug("distributed Alpha Vantage limiter unavailable", exc_info=True)
            await self.rate_limiter.aacquire()
            try:
                response = await self._client.get(self.config.base_url, params=query)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = TransientError(f"Transport error: {exc}")
                await asyncio.sleep(self._sleep_seconds(attempt))
                continue
            payload, err = self._process_response(response, datatype=datatype)
            if err is None:
                return payload
            if isinstance(err, RateLimitError) and err.kind == RateLimitKind.RPM:
                last_exc = err
                await asyncio.sleep(self._sleep_seconds(attempt, err.retry_after_seconds))
                continue
            if isinstance(err, TransientError):
                last_exc = err
                await asyncio.sleep(self._sleep_seconds(attempt))
                continue
            raise err
        raise last_exc or TransientError("Unknown Alpha Vantage transport failure")


def _sleep_sync(seconds: float) -> None:
    import time

    time.sleep(max(0.0, seconds))


def _parse_retry_after(headers: Mapping[str, str]) -> float | None:
    raw = headers.get("Retry-After") or headers.get("retry-after")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        try:
            dt = parsedate_to_datetime(raw)
            return max(0.0, dt.timestamp())
        except Exception:
            return None


__all__ = ["AsyncTransport", "Transport", "TransportConfig"]
