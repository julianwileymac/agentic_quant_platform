"""Databento historical HTTP — incremental append-only.

Endpoint: ``POST https://hist.databento.com/v0/timeseries.get_range``
Rate-limit class: ``databento.historical``
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Iterable

from aqp_ingest_cdk.cursors import PointInTimeIncrementalCursor
from aqp_ingest_cdk.streams import RateLimitedHttpStream


class DatabentoHistoricalStream(RateLimitedHttpStream):
    """Per-symbol Databento historical slice."""

    url_base = "https://hist.databento.com"
    primary_key = ["ts_event", "instrument_id"]
    cursor_field = "ts_event"
    http_method = "POST"

    rate_limit_service = "databento.historical"

    def __init__(
        self,
        *,
        api_key: str,
        dataset: str,
        schema: str,
        symbols: list[str],
        lookback_days: int = 7,
        owner_user_id: str = "anonymous",
        rate_limit_key_id: str = "primary",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._api_key = api_key
        self._dataset = dataset
        self._schema = schema
        self._symbols = list(symbols)
        self._lookback_days = lookback_days
        self.config = {  # type: ignore[attr-defined]
            "_aqp_owner_user_id": owner_user_id,
            "_aqp_rate_limit_key_id": rate_limit_key_id,
            "_aqp_rate_limit_service": self.rate_limit_service,
        }

    def path(self, **_):  # type: ignore[override]
        return "/v0/timeseries.get_range"

    def request_headers(self, **_) -> dict[str, str]:  # type: ignore[override]
        import base64

        token = base64.b64encode(f"{self._api_key}:".encode()).decode()
        return {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
        }

    def request_body_data(self, stream_slice, **_) -> str:  # type: ignore[override]
        return json.dumps(
            {
                "dataset": self._dataset,
                "schema": self._schema,
                "symbols": [stream_slice["key"]],
                "start": stream_slice["from"],
                "end": stream_slice["to"],
                "encoding": "json",
            }
        )

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
        for line in response.iter_lines():
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            rec.setdefault("symbol", stream_slice["key"])
            yield rec


__all__ = ["DatabentoHistoricalStream"]
