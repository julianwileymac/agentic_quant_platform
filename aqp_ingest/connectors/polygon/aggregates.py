"""Polygon.io aggregates (OHLCV bars) — incremental append+dedup.

Endpoint: ``GET /v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{from}/{to}``
Rate-limit class: ``polygon.aggregates``
Cursor: ``t`` (epoch-ms Unix timestamp of bar start)
Primary key: ``(ticker, t)``
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Iterable

from aqp_ingest_cdk.cursors import PointInTimeIncrementalCursor
from aqp_ingest_cdk.streams import RateLimitedHttpStream

logger = logging.getLogger(__name__)


class PolygonAggregatesStream(RateLimitedHttpStream):
    """Per-ticker, per-day OHLCV bar slices."""

    url_base = "https://api.polygon.io"
    primary_key = ["ticker", "t"]
    cursor_field = "t"

    rate_limit_service = "polygon.aggregates"
    rate_limit_tokens_per_call = 1

    def __init__(
        self,
        *,
        api_key: str,
        tickers: list[str],
        timespan: str = "minute",
        multiplier: int = 1,
        lookback_days: int = 30,
        page_limit: int = 50_000,
        owner_user_id: str = "anonymous",
        rate_limit_key_id: str = "primary",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._api_key = api_key
        self._tickers = list(tickers)
        self._timespan = timespan
        self._multiplier = multiplier
        self._lookback_days = lookback_days
        self._page_limit = page_limit
        self.config = {  # type: ignore[attr-defined]
            "_aqp_owner_user_id": owner_user_id,
            "_aqp_rate_limit_key_id": rate_limit_key_id,
            "_aqp_rate_limit_service": self.rate_limit_service,
        }

    def path(self, stream_slice, **_):  # type: ignore[override]
        return (
            f"/v2/aggs/ticker/{stream_slice['key']}/range/"
            f"{self._multiplier}/{self._timespan}/"
            f"{stream_slice['from']}/{stream_slice['to']}"
        )

    def request_params(self, **_):  # type: ignore[override]
        return {
            "adjusted": "true",
            "sort": "asc",
            "limit": int(self._page_limit),
            "apiKey": self._api_key,
        }

    def stream_slices(  # type: ignore[override]
        self,
        sync_mode=None,
        cursor_field=None,
        stream_state=None,
    ) -> Iterable[dict[str, str]]:
        cursor = PointInTimeIncrementalCursor.from_state(
            self.cursor_field, stream_state
        )
        end = datetime.utcnow()
        start = end - timedelta(days=self._lookback_days)
        yield from cursor.iter_partitions(
            keys=self._tickers,
            start=start,
            end=end,
            step_days=1,
        )

    def parse_response(self, response, stream_slice, **_):  # type: ignore[override]
        payload = response.json()
        ticker = stream_slice["key"]
        for row in payload.get("results", []) or []:
            yield {
                "ticker": ticker,
                "t": row.get("t"),
                "o": row.get("o"),
                "h": row.get("h"),
                "l": row.get("l"),
                "c": row.get("c"),
                "v": row.get("v"),
                "vw": row.get("vw"),
                "n": row.get("n"),
            }


__all__ = ["PolygonAggregatesStream"]
