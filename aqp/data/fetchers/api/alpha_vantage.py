"""Alpha Vantage fetcher.

Wraps :class:`aqp.data.sources.alpha_vantage.client.AlphaVantageClient`
so any AV endpoint becomes an engine source. ``function`` selects which
AV endpoint to call (``TIME_SERIES_INTRADAY``, ``TIME_SERIES_DAILY``,
``GLOBAL_QUOTE``, etc.).
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from aqp.data.engine.nodes import NodeContext
from aqp.data.fetchers.base import (
    Fetcher,
    FetcherCapability,
    FetcherKind,
    RateLimit,
    register_source_fetcher,
)

logger = logging.getLogger(__name__)


if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


@register_source_fetcher(
    "source.alpha_vantage",
    display_name="Alpha Vantage",
    kind=FetcherKind.API,
    description="Generic Alpha Vantage endpoint fetcher.",
    base_url="https://www.alphavantage.co/query",
    auth_type="api_key",
    credentials_ref="AQP_ALPHA_VANTAGE_API_KEY",
    rate_limit=RateLimit(requests_per_minute=75),
    capabilities=(
        FetcherCapability.SUPPORTS_INCREMENTAL.value,
        FetcherCapability.REQUIRES_AUTH.value,
        FetcherCapability.SUPPORTS_RATE_LIMIT.value,
    ),
    domains=(
        "market.bars",
        "market.quotes",
        "fundamentals.overview",
        "fundamentals.statements",
        "news.sentiment",
        "fx",
        "crypto",
    ),
)
class AlphaVantageFetcher(Fetcher):
    """Stream Alpha Vantage endpoint output as Arrow batches."""

    capabilities = (
        FetcherCapability.SUPPORTS_INCREMENTAL,
        FetcherCapability.REQUIRES_AUTH,
        FetcherCapability.SUPPORTS_RATE_LIMIT,
    )
    default_rate_limit = RateLimit(requests_per_minute=75)

    def __init__(
        self,
        *,
        function: str,
        symbol: str | None = None,
        params: dict[str, Any] | None = None,
        chunk_rows: int = 50_000,
        **kwargs: Any,
    ) -> None:
        super().__init__(chunk_rows=chunk_rows, **kwargs)
        if not function:
            raise ValueError("AlphaVantageFetcher: function required")
        self.function = function.upper()
        self.symbol = symbol
        self.params = dict(params or {})
        self.chunk_rows = max(1, int(chunk_rows))

    def source_uri(self) -> str | None:
        return f"alpha_vantage://{self.function}/{self.symbol or ''}"

    def fetch(self, ctx: NodeContext) -> Iterator[pa.RecordBatch]:
        try:
            from aqp.data.sources.alpha_vantage.client import AlphaVantageClient
        except Exception as exc:  # noqa: BLE001
            logger.warning("AlphaVantageFetcher unavailable: %s", exc)
            return
        try:
            import pandas as pd
        except Exception as exc:  # noqa: BLE001
            logger.warning("AlphaVantageFetcher requires pandas: %s", exc)
            return

        client = AlphaVantageClient()
        ctx.emit("source", f"alpha_vantage function={self.function} symbol={self.symbol}")
        params: dict[str, Any] = {"function": self.function, **self.params}
        if self.symbol:
            params.setdefault("symbol", self.symbol)
        try:
            payload = client.request(**params)
        except Exception as exc:  # noqa: BLE001 - keep retry semantics
            logger.warning("alpha_vantage request failed: %s", exc)
            raise

        df = self._payload_to_dataframe(pd, payload)
        if df is None or len(df) == 0:
            return
        if self.symbol and "symbol" not in df.columns:
            df["symbol"] = self.symbol
        yield from self.from_pandas(df, chunk_rows=self.chunk_rows)

    @staticmethod
    def _payload_to_dataframe(pd, payload: Any):  # type: ignore[no-untyped-def]
        if isinstance(payload, list):
            return pd.DataFrame(payload)
        if not isinstance(payload, dict):
            return pd.DataFrame()
        # Heuristic: AV often returns a top-level series under a key.
        for key, value in payload.items():
            if isinstance(value, dict) and value and all(
                isinstance(v, dict) for v in value.values()
            ):
                df = pd.DataFrame.from_dict(value, orient="index")
                df.index.name = "observation_date"
                return df.reset_index()
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return pd.DataFrame(value)
        # Fall back to flat single-row payload.
        return pd.DataFrame([payload])
