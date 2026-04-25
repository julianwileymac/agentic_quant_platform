"""Rich Alpha Vantage sync/async client facade."""
from __future__ import annotations

from io import StringIO
from typing import Any, Iterable

import httpx
import pandas as pd

from aqp.config import settings
from aqp.data.sources.alpha_vantage._cache import CacheBackend, MemoryCache, make_cache
from aqp.data.sources.alpha_vantage._credentials import load_api_key
from aqp.data.sources.alpha_vantage._errors import (
    AlphaVantageClientError,
    AlphaVantageError,
    InvalidApiKeyError,
    RateLimitError,
)
from aqp.data.sources.alpha_vantage._rate_limiter import RateLimiter
from aqp.data.sources.alpha_vantage._transport import AsyncTransport, Transport, TransportConfig
from aqp.data.sources.alpha_vantage.endpoints import (
    Commodities,
    Crypto,
    Economics,
    Forex,
    Fundamentals,
    Indices,
    Intelligence,
    Options,
    Technicals,
    TimeSeries,
)


class AlphaVantageClient:
    """Unified sync + async facade for the Alpha Vantage REST API."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        api_key_file: str | None = None,
        extra_api_key_paths: Iterable[str | None] | None = None,
        base_url: str | None = None,
        rate_limit_rpm: int | None = None,
        daily_limit: int | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        backoff_base: float = 1.0,
        backoff_cap: float = 60.0,
        endpoint: str | None = None,
        timeout: float | None = None,
        headers: dict[str, str] | None = None,
        cache: CacheBackend | None = None,
        cache_backend: str | None = None,
        cache_redis_client: Any = None,
        cache_sqlite_path: str | None = None,
        cache_max_entries: int | None = None,
        rapidapi: bool | None = None,
        rapidapi_host: str = "alpha-vantage.p.rapidapi.com",
        sync_client: httpx.Client | None = None,
        async_client: httpx.AsyncClient | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self.api_key = load_api_key(
            api_key,
            file_path=api_key_file,
            extra_paths=extra_api_key_paths,
            strict=True,
        )
        self.endpoint = endpoint or base_url or getattr(
            settings,
            "alpha_vantage_base_url",
            "https://www.alphavantage.co/query",
        )
        self.timeout = float(
            timeout
            if timeout is not None
            else timeout_seconds
            if timeout_seconds is not None
            else getattr(settings, "alpha_vantage_timeout_seconds", 30.0)
        )
        max_entries = int(cache_max_entries or getattr(settings, "alpha_vantage_cache_max_entries", 512))
        backend = str(cache_backend or getattr(settings, "alpha_vantage_cache_backend", "memory"))
        if cache is None:
            if backend == "memory" and cache_redis_client is None and cache_sqlite_path is None:
                cache = MemoryCache(max_entries=max_entries)
            else:
                cache = make_cache(
                    backend,
                    redis_client=cache_redis_client,
                    sqlite_path=cache_sqlite_path,
                    max_entries=max_entries,
                )
        self._rate_limiter = rate_limiter or RateLimiter(
            rpm=int(rate_limit_rpm or getattr(settings, "alpha_vantage_rpm_limit", 75)),
            daily=int(daily_limit if daily_limit is not None else getattr(settings, "alpha_vantage_daily_limit", 0)),
        )
        config = TransportConfig(
            base_url=self.endpoint,
            timeout_seconds=self.timeout,
            max_retries=int(max_retries if max_retries is not None else getattr(settings, "alpha_vantage_max_retries", 5)),
            backoff_base=backoff_base,
            backoff_cap=backoff_cap,
            headers=headers or {},
            rapidapi=bool(rapidapi if rapidapi is not None else getattr(settings, "alpha_vantage_rapidapi", False)),
            rapidapi_host=rapidapi_host,
        )
        self._sync = Transport(
            self.api_key,
            rate_limiter=self._rate_limiter,
            cache=cache,
            config=config,
            client=sync_client,
        )
        self._async = AsyncTransport(
            self.api_key,
            rate_limiter=self._rate_limiter,
            cache=cache,
            config=config,
            client=async_client,
        )
        self.timeseries = TimeSeries(transport=self._sync, async_transport=self._async)
        self.fundamentals = Fundamentals(transport=self._sync, async_transport=self._async)
        self.intelligence = Intelligence(transport=self._sync, async_transport=self._async)
        self.forex = Forex(transport=self._sync, async_transport=self._async)
        self.crypto = Crypto(transport=self._sync, async_transport=self._async)
        self.options = Options(transport=self._sync, async_transport=self._async)
        self.commodities = Commodities(transport=self._sync, async_transport=self._async)
        self.economics = Economics(transport=self._sync, async_transport=self._async)
        self.technicals = Technicals(transport=self._sync, async_transport=self._async)
        self.indices = Indices(transport=self._sync, async_transport=self._async)

    @property
    def rate_limiter(self) -> RateLimiter:
        return self._rate_limiter

    def close(self) -> None:
        self._sync.close()

    async def aclose(self) -> None:
        await self._async.aclose()

    def __enter__(self) -> "AlphaVantageClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    async def __aenter__(self) -> "AlphaVantageClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    def _json(self, *, function: str, **params: Any) -> dict[str, Any]:
        payload = self._sync.request({"function": function, **params})
        if not isinstance(payload, dict):
            raise AlphaVantageClientError("Alpha Vantage returned malformed JSON payload")
        return payload

    def _csv(self, *, function: str, **params: Any) -> pd.DataFrame:
        payload = self._sync.request({"function": function, **params}, datatype="csv")
        body = str(payload or "").strip()
        if not body:
            return pd.DataFrame()
        try:
            return pd.read_csv(StringIO(body))
        except Exception as exc:
            raise AlphaVantageClientError(f"failed to parse CSV payload: {exc}") from exc

    def listing_status(self, *, state: str = "active", date: str | None = None) -> pd.DataFrame:
        return self._csv(function="LISTING_STATUS", state=state, date=date)

    def overview(self, symbol: str) -> dict[str, Any]:
        return self.fundamentals.overview(symbol).model_dump()

    def global_quote(self, symbol: str) -> dict[str, Any]:
        return {"Global Quote": self.timeseries.global_quote(symbol).model_dump()}

    def symbol_search(self, keywords: str) -> list[dict[str, Any]]:
        return [row.model_dump() for row in self.timeseries.search(keywords)]


__all__ = [
    "AlphaVantageClient",
    "AlphaVantageClientError",
    "AlphaVantageError",
    "InvalidApiKeyError",
    "RateLimitError",
    "RateLimiter",
    "load_api_key",
]
