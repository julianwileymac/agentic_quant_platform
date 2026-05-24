"""Alpaca trades — incremental append-only."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable

from aqp_ingest_cdk.cursors import PointInTimeIncrementalCursor
from aqp_ingest_cdk.streams import RateLimitedHttpStream


class AlpacaTradesStream(RateLimitedHttpStream):
    """Per-symbol Alpaca trade tick slice."""

    url_base = "https://data.alpaca.markets"
    primary_key = ["symbol", "t", "i"]
    cursor_field = "t"

    rate_limit_service = "alpaca.trades"

    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        symbols: list[str],
        lookback_days: int = 1,
        page_limit: int = 10_000,
        owner_user_id: str = "anonymous",
        rate_limit_key_id: str = "primary",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._api_key = api_key
        self._api_secret = api_secret
        self._symbols = list(symbols)
        self._lookback_days = lookback_days
        self._page_limit = page_limit
        self.config = {  # type: ignore[attr-defined]
            "_aqp_owner_user_id": owner_user_id,
            "_aqp_rate_limit_key_id": rate_limit_key_id,
            "_aqp_rate_limit_service": self.rate_limit_service,
        }

    def path(self, stream_slice, **_):  # type: ignore[override]
        return f"/v2/stocks/{stream_slice['key']}/trades"

    def request_headers(self, **_) -> dict[str, str]:  # type: ignore[override]
        return {
            "APCA-API-KEY-ID": self._api_key,
            "APCA-API-SECRET-KEY": self._api_secret,
        }

    def request_params(self, stream_slice, **_):  # type: ignore[override]
        return {
            "start": stream_slice["from"],
            "end": stream_slice["to"],
            "limit": int(self._page_limit),
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
            keys=self._symbols,
            start=start,
            end=end,
            step_days=1,
        )

    def parse_response(self, response, stream_slice, **_):  # type: ignore[override]
        payload = response.json()
        for row in payload.get("trades", []) or []:
            row.setdefault("symbol", stream_slice["key"])
            yield row


__all__ = ["AlpacaTradesStream"]
