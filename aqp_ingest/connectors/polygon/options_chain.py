"""Polygon.io options chain snapshots — incremental append+dedup.

Endpoint: ``GET /v3/snapshot/options/{underlying}``
Rate-limit class: ``polygon.options``
Cursor: ``snapshot_at`` (ISO-8601; the connector stamps it per call)
Primary key: ``(underlying, ticker, snapshot_at)``
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from aqp_ingest_cdk.streams import RateLimitedHttpStream


class PolygonOptionsChainStream(RateLimitedHttpStream):
    """Per-underlying full options chain snapshot."""

    url_base = "https://api.polygon.io"
    primary_key = ["underlying", "ticker", "snapshot_at"]
    cursor_field = "snapshot_at"

    rate_limit_service = "polygon.options"

    def __init__(
        self,
        *,
        api_key: str,
        underlyings: list[str],
        owner_user_id: str = "anonymous",
        rate_limit_key_id: str = "primary",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._api_key = api_key
        self._underlyings = list(underlyings)
        self.config = {  # type: ignore[attr-defined]
            "_aqp_owner_user_id": owner_user_id,
            "_aqp_rate_limit_key_id": rate_limit_key_id,
            "_aqp_rate_limit_service": self.rate_limit_service,
        }

    def path(self, stream_slice, **_):  # type: ignore[override]
        return f"/v3/snapshot/options/{stream_slice['underlying']}"

    def request_params(self, **_):  # type: ignore[override]
        return {"apiKey": self._api_key, "limit": 250}

    def stream_slices(  # type: ignore[override]
        self,
        sync_mode=None,
        cursor_field=None,
        stream_state=None,
    ):
        for underlying in self._underlyings:
            yield {"underlying": underlying}

    def parse_response(self, response, stream_slice, **_):  # type: ignore[override]
        snapshot_at = datetime.utcnow().isoformat()
        payload = response.json()
        for row in payload.get("results", []) or []:
            yield {
                "underlying": stream_slice["underlying"],
                "ticker": (row.get("details") or {}).get("ticker"),
                "snapshot_at": snapshot_at,
                "raw": row,
            }


__all__ = ["PolygonOptionsChainStream"]
