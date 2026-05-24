"""IEX Cloud snapshots — full refresh per call.

Endpoint: ``GET https://cloud.iexapis.com/stable/stock/{symbol}/quote``
Rate-limit class: ``iex.snapshots``
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from aqp_ingest_cdk.streams import RateLimitedHttpStream


class IEXCloudSnapshotsStream(RateLimitedHttpStream):
    """Per-symbol IEX quote snapshot."""

    url_base = "https://cloud.iexapis.com"
    primary_key = ["symbol", "snapshot_at"]
    cursor_field = "snapshot_at"

    rate_limit_service = "iex.snapshots"

    def __init__(
        self,
        *,
        api_key: str,
        symbols: list[str],
        owner_user_id: str = "anonymous",
        rate_limit_key_id: str = "primary",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._api_key = api_key
        self._symbols = list(symbols)
        self.config = {  # type: ignore[attr-defined]
            "_aqp_owner_user_id": owner_user_id,
            "_aqp_rate_limit_key_id": rate_limit_key_id,
            "_aqp_rate_limit_service": self.rate_limit_service,
        }

    def path(self, stream_slice, **_):  # type: ignore[override]
        return f"/stable/stock/{stream_slice['symbol']}/quote"

    def request_params(self, **_):  # type: ignore[override]
        return {"token": self._api_key}

    def stream_slices(  # type: ignore[override]
        self,
        sync_mode=None,
        cursor_field=None,
        stream_state=None,
    ):
        for sym in self._symbols:
            yield {"symbol": sym}

    def parse_response(self, response, stream_slice, **_):  # type: ignore[override]
        payload = response.json()
        if not isinstance(payload, dict):
            return
        payload["symbol"] = stream_slice["symbol"]
        payload["snapshot_at"] = datetime.utcnow().isoformat()
        yield payload


__all__ = ["IEXCloudSnapshotsStream"]
