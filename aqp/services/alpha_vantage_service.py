"""AQP service facade for Alpha Vantage."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Sequence

from aqp.config import Settings, settings
from aqp.data.sources.alpha_vantage import (
    AlphaVantageClient,
    AlphaVantageClientError,
    InvalidApiKeyError,
    RateLimiter,
    load_api_key,
)
from aqp.data.sources.alpha_vantage._cache import MemoryCache, RedisCache

logger = logging.getLogger(__name__)


class AlphaVantageService:
    """Async bridge between FastAPI handlers and the Alpha Vantage client."""

    def __init__(self, cfg: Settings | None = None, *, redis_client: Any | None = None) -> None:
        self.settings = cfg or settings
        self._redis_client = redis_client
        self._client: AlphaVantageClient | None = None
        self._client_lock = asyncio.Lock()
        self._credentials_error: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(getattr(self.settings, "alpha_vantage_enabled", True))

    async def _get_client(self) -> AlphaVantageClient:
        if not self.enabled:
            raise RuntimeError("Alpha Vantage integration disabled")
        if self._client is not None:
            return self._client
        async with self._client_lock:
            if self._client is None:
                self._client = await asyncio.to_thread(self._build_client)
        return self._client

    def _build_client(self) -> AlphaVantageClient:
        cache = None
        cache_backend = str(getattr(self.settings, "alpha_vantage_cache_backend", "memory")).lower()
        if cache_backend == "redis" and self._redis_client is not None:
            cache = RedisCache(self._redis_client)
        elif cache_backend == "memory":
            cache = MemoryCache(
                max_entries=int(getattr(self.settings, "alpha_vantage_cache_max_entries", 512)),
            )
        try:
            return AlphaVantageClient(
                api_key=getattr(self.settings, "alpha_vantage_api_key", ""),
                api_key_file=getattr(self.settings, "alpha_vantage_api_key_file", ""),
                base_url=getattr(self.settings, "alpha_vantage_base_url", "https://www.alphavantage.co/query"),
                rate_limit_rpm=int(getattr(self.settings, "alpha_vantage_rpm_limit", 75)),
                daily_limit=int(getattr(self.settings, "alpha_vantage_daily_limit", 0)),
                timeout_seconds=float(getattr(self.settings, "alpha_vantage_timeout_seconds", 30.0)),
                max_retries=int(getattr(self.settings, "alpha_vantage_max_retries", 5)),
                cache=cache,
                cache_backend=cache_backend,
                rapidapi=bool(getattr(self.settings, "alpha_vantage_rapidapi", False)),
            )
        except InvalidApiKeyError as exc:
            self._credentials_error = str(exc)
            raise

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def health(self) -> dict[str, Any]:
        message = None
        try:
            key = await asyncio.to_thread(
                load_api_key,
                getattr(self.settings, "alpha_vantage_api_key", ""),
                file_path=getattr(self.settings, "alpha_vantage_api_key_file", ""),
                strict=False,
            )
            credentials_loaded = bool(key)
            if not credentials_loaded:
                message = "API key not resolved"
        except Exception as exc:  # pragma: no cover - defensive
            credentials_loaded = False
            message = str(exc)
        return {
            "enabled": self.enabled,
            "credentials_loaded": credentials_loaded,
            "base_url": getattr(self.settings, "alpha_vantage_base_url", "https://www.alphavantage.co/query"),
            "rpm_limit": int(getattr(self.settings, "alpha_vantage_rpm_limit", 75)),
            "daily_limit": int(getattr(self.settings, "alpha_vantage_daily_limit", 0)),
            "cache_backend": getattr(self.settings, "alpha_vantage_cache_backend", "memory"),
            "client_available": True,
            "client_version": "aqp",
            "message": message or self._credentials_error,
        }

    async def usage(self) -> dict[str, Any]:
        client = await self._get_client()
        snap = await asyncio.to_thread(client.rate_limiter.snapshot)
        return snap.__dict__

    async def timeseries(self, function: str, **params: Any) -> Any:
        client = await self._get_client()
        ts = client.timeseries
        dispatch = {
            "intraday": ts.aintraday,
            "daily": ts.adaily,
            "daily_adjusted": ts.adaily_adjusted,
            "weekly": ts.aweekly,
            "weekly_adjusted": ts.aweekly_adjusted,
            "monthly": ts.amonthly,
            "monthly_adjusted": ts.amonthly_adjusted,
        }
        if function == "global_quote":
            return _serialize(await ts.aglobal_quote(params["symbol"], entitlement=params.get("entitlement")))
        if function == "bulk_quotes":
            symbols = params.get("symbols") or []
            return await ts.arealtime_bulk_quotes(symbols, entitlement=params.get("entitlement"))
        if function not in dispatch:
            raise ValueError(f"Unsupported timeseries function: {function}")
        return _serialize(await dispatch[function](**_prune(params)))

    async def symbol_search(self, keywords: str) -> list[dict[str, Any]]:
        client = await self._get_client()
        return [_serialize(row) for row in await client.timeseries.asearch(keywords)]

    async def market_status(self) -> dict[str, Any]:
        client = await self._get_client()
        return _serialize(await client.timeseries.amarket_status())

    async def fundamentals(self, kind: str, **params: Any) -> Any:
        client = await self._get_client()
        f = client.fundamentals
        symbol = params.get("symbol", "")
        dispatch = {
            "overview": (f.aoverview, (symbol,)),
            "etf": (f.aetf_profile, (symbol,)),
            "dividends": (f.adividends, (symbol,)),
            "splits": (f.asplits, (symbol,)),
            "income": (f.aincome_statement, (symbol,)),
            "balance": (f.abalance_sheet, (symbol,)),
            "cashflow": (f.acash_flow, (symbol,)),
            "earnings": (f.aearnings, (symbol,)),
            "estimates": (f.aearnings_estimates, (symbol,)),
            "shares": (f.ashares_outstanding, (symbol,)),
        }
        if kind in dispatch:
            func, args = dispatch[kind]
            return _serialize(await func(*args))
        if kind == "ipo":
            return await f.aipo_calendar()
        if kind == "earnings_calendar":
            return await f.aearnings_calendar(symbol=params.get("symbol"), horizon=params.get("horizon"))
        if kind == "listing":
            return await f.alisting_status(date=params.get("date"), state=params.get("state"))
        raise ValueError(f"Unsupported fundamentals kind: {kind}")

    async def intelligence(self, kind: str, **params: Any) -> Any:
        client = await self._get_client()
        ai = client.intelligence
        if kind == "news":
            return _serialize(await ai.anews(**_prune(params)))
        if kind == "transcript":
            return _serialize(await ai.aearnings_transcript(params["symbol"], params["quarter"]))
        if kind == "top-movers":
            return _serialize(await ai.atop_movers(entitlement=params.get("entitlement")))
        if kind == "insider":
            return [_serialize(row) for row in await ai.ainsider(params["symbol"])]
        if kind == "institutional":
            return [_serialize(row) for row in await ai.ainstitutional(params["symbol"])]
        if kind == "analytics-fixed":
            return _serialize(await ai.aanalytics_fixed(**_prune(params)))
        if kind == "analytics-sliding":
            return _serialize(await ai.aanalytics_sliding(**_prune(params)))
        raise ValueError(f"Unsupported intelligence kind: {kind}")

    async def forex(self, kind: str, **params: Any) -> Any:
        client = await self._get_client()
        fx = client.forex
        if kind == "rate":
            return _serialize(await fx.aexchange_rate(params["from_currency"], params["to_currency"]))
        if kind == "intraday":
            return _serialize(await fx.aintraday(**_prune(params)))
        if kind == "daily":
            return _serialize(await fx.adaily(**_prune(params)))
        if kind == "weekly":
            return _serialize(await fx.aweekly(**_prune(params)))
        if kind == "monthly":
            return _serialize(await fx.amonthly(**_prune(params)))
        raise ValueError(f"Unsupported forex kind: {kind}")

    async def crypto(self, kind: str, **params: Any) -> Any:
        client = await self._get_client()
        c = client.crypto
        if kind == "rate":
            return _serialize(await c.aexchange_rate(params["symbol"], params["market"]))
        if kind == "intraday":
            return _serialize(await c.aintraday(**_prune(params)))
        if kind == "daily":
            return _serialize(await c.adaily(params["symbol"], params["market"]))
        if kind == "weekly":
            return _serialize(await c.aweekly(params["symbol"], params["market"]))
        if kind == "monthly":
            return _serialize(await c.amonthly(params["symbol"], params["market"]))
        raise ValueError(f"Unsupported crypto kind: {kind}")

    async def options(self, kind: str, **params: Any) -> Any:
        client = await self._get_client()
        o = client.options
        if kind == "realtime":
            return _serialize(await o.arealtime(params["symbol"], contract=params.get("contract")))
        if kind == "historical":
            return _serialize(await o.ahistorical(params["symbol"], date=params.get("date")))
        if kind == "pcr-realtime":
            return [_serialize(row) for row in await o.arealtime_put_call_ratio(params["symbol"])]
        if kind == "pcr-historical":
            return [_serialize(row) for row in await o.ahistorical_put_call_ratio(params["symbol"], date=params.get("date"))]
        if kind == "voi-realtime":
            return [_serialize(row) for row in await o.arealtime_voi_ratio(params["symbol"])]
        if kind == "voi-historical":
            return [_serialize(row) for row in await o.ahistorical_voi_ratio(params["symbol"], date=params.get("date"))]
        raise ValueError(f"Unsupported options kind: {kind}")

    async def commodities(self, name: str, **params: Any) -> Any:
        client = await self._get_client()
        return _serialize(await client.commodities.aby_name(name, **_prune(params)))

    async def economics(self, indicator: str, **params: Any) -> Any:
        client = await self._get_client()
        return _serialize(await client.economics.aby_name(indicator, **_prune(params)))

    async def technicals(self, indicator: str, symbol: str, **params: Any) -> Any:
        client = await self._get_client()
        return _serialize(await client.technicals.aget(indicator, symbol, **_prune(params)))

    async def indices(self, key: str, **params: Any) -> Any:
        client = await self._get_client()
        return _serialize(await client.indices.aget(key, **_prune(params)))

    async def index_catalog(self) -> list[dict[str, Any]]:
        client = await self._get_client()
        return [_serialize(row) for row in await client.indices.acatalog()]

    def submit_bulk_task(
        self,
        *,
        category: str,
        symbols: Sequence[str],
        date_range: dict[str, str] | None = None,
        extra_params: dict[str, Any] | None = None,
        target_bucket: str | None = None,
    ) -> dict[str, Any]:
        from aqp.tasks.ingestion_tasks import alpha_vantage_bulk_load

        async_result = alpha_vantage_bulk_load.delay(
            category,
            list(symbols),
            date_range or {},
            extra_params or {},
            target_bucket,
        )
        submitted_at = datetime.now(timezone.utc).isoformat()
        return {
            "task_id": async_result.id,
            "status": "queued",
            "submitted_at": submitted_at,
            "category": category,
            "symbols": list(symbols),
            "stream_url": f"/chat/stream/{async_result.id}",
        }


def _prune(params: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in params.items() if v is not None and v != ""}


def _serialize(obj: Any) -> Any:
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, list):
        return [_serialize(row) for row in obj]
    if isinstance(obj, dict):
        return {key: _serialize(value) for key, value in obj.items()}
    return obj


__all__ = ["AlphaVantageService", "AlphaVantageClientError", "RateLimiter"]
