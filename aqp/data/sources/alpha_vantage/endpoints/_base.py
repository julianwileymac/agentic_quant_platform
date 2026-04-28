"""Endpoint helpers shared by Alpha Vantage resource groups."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import pandas as pd

from aqp.data.sources.alpha_vantage._parsers import normalize_mapping
from aqp.data.sources.alpha_vantage._transport import AsyncTransport, Transport
from aqp.data.sources.alpha_vantage.models import AVModel, TimeSeriesPayload

logger = logging.getLogger(__name__)

_STOCK_INTRADAY_INTERVALS = frozenset({"1min", "5min", "15min", "30min", "60min"})
_STOCK_INTRADAY_ALIASES: dict[str, str] = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "60m": "60min",
    "1h": "60min",
}


class BaseEndpoint:
    def __init__(self, *, transport: Transport, async_transport: AsyncTransport) -> None:
        self._transport = transport
        self._async_transport = async_transport

    def _sync_request(
        self,
        params: Mapping[str, Any],
        *,
        datatype: str | None = None,
        cache: bool = True,
    ) -> Any:
        query, use_cache, cache_ttl = _request_options(params, cache)
        return self._transport.request(
            query,
            datatype=datatype,
            cache=use_cache,
            cache_ttl=cache_ttl,
        )

    async def _async_request(
        self,
        params: Mapping[str, Any],
        *,
        datatype: str | None = None,
        cache: bool = True,
    ) -> Any:
        query, use_cache, cache_ttl = _request_options(params, cache)
        return await self._async_transport.request(
            query,
            datatype=datatype,
            cache=use_cache,
            cache_ttl=cache_ttl,
        )

    @staticmethod
    def _model(payload: Any) -> AVModel:
        if isinstance(payload, AVModel):
            return payload
        if isinstance(payload, dict):
            return AVModel.model_validate(payload)
        return AVModel.model_validate({"data": payload})

    @staticmethod
    def _csv_frame(payload: str) -> pd.DataFrame:
        from io import StringIO

        body = str(payload or "").strip()
        if not body:
            return pd.DataFrame()
        return pd.read_csv(StringIO(body))

    @staticmethod
    def _time_series(payload: dict[str, Any]) -> TimeSeriesPayload:
        metadata = {}
        bars: list[dict[str, Any]] = []
        for key, value in payload.items():
            if str(key).lower().startswith("meta data") and isinstance(value, dict):
                metadata = normalize_mapping(value)
                continue
            if "time series" in str(key).lower() and isinstance(value, dict):
                for ts, row in value.items():
                    if isinstance(row, dict):
                        bars.append({"timestamp": ts, **normalize_mapping(row)})
        return TimeSeriesPayload(metadata=metadata, bars=bars)


def _prune(params: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in params.items() if v is not None and v != ""}


def coerce_stock_intraday_interval(interval: str | None) -> str:
    """Return a ``TIME_SERIES_INTRADAY`` interval Alpha Vantage accepts.

    Callers often pass ``None`` (explicit or from JSON), which would otherwise be
    pruned from the query string and trigger Alpha Vantage's *Invalid API call*
    for intraday. UI-style tokens like ``1d`` or ``5m`` are normalized.
    """
    if interval is None:
        return "5min"
    raw = str(interval).strip().lower()
    if not raw:
        return "5min"
    raw = _STOCK_INTRADAY_ALIASES.get(raw, raw)
    if raw in _STOCK_INTRADAY_INTERVALS:
        return raw
    logger.warning(
        "Unsupported stock intraday interval %r; defaulting to 5min (expected one of %s)",
        interval,
        ", ".join(sorted(_STOCK_INTRADAY_INTERVALS)),
    )
    return "5min"


def _request_options(params: Mapping[str, Any], default_cache: bool) -> tuple[dict[str, Any], bool, float | None]:
    """Split AQP-private transport controls from Alpha Vantage query params."""
    query = dict(params)
    cache_raw = query.pop("_cache", default_cache)
    cache_ttl_raw = query.pop("_cache_ttl", None)
    try:
        cache_ttl = float(cache_ttl_raw) if cache_ttl_raw is not None else None
    except (TypeError, ValueError):
        cache_ttl = None
    return query, bool(cache_raw), cache_ttl


__all__ = ["BaseEndpoint", "_prune", "coerce_stock_intraday_interval"]
