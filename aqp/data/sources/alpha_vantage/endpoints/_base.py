"""Endpoint helpers shared by Alpha Vantage resource groups."""
from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from aqp.data.sources.alpha_vantage._parsers import normalize_mapping
from aqp.data.sources.alpha_vantage._transport import AsyncTransport, Transport
from aqp.data.sources.alpha_vantage.models import AVModel, TimeSeriesPayload


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
        return self._transport.request(params, datatype=datatype, cache=cache)

    async def _async_request(
        self,
        params: Mapping[str, Any],
        *,
        datatype: str | None = None,
        cache: bool = True,
    ) -> Any:
        return await self._async_transport.request(params, datatype=datatype, cache=cache)

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


__all__ = ["BaseEndpoint", "_prune"]
