"""Alpha Vantage ingester -> Kafka.

Polls the Alpha Vantage REST API (no WebSocket) for intraday bars
across the configured universe and publishes them onto
``market.bar.v1`` so the downstream Flink topology can normalise
them into ``aqp_silver_equities_bars`` (canonical AQP silver feed).

Rate limits
-----------

Alpha Vantage's free tier caps requests at 5/min and 500/day. The
ingester defaults to a 12-second sleep between requests so even a
free-tier deployment can sweep 5 symbols/minute indefinitely. Paid
tiers can override the cadence via
``AQP_ALPHAVANTAGE_REQUEST_INTERVAL_SECONDS``.

Operating modes
---------------

- ``mode='intraday'`` (default): polls ``TIME_SERIES_INTRADAY`` with
  the configured ``interval`` (``"1min"`` / ``"5min"`` / ``"15min"``
  / ``"30min"`` / ``"60min"``).
- ``mode='quote'``: polls ``GLOBAL_QUOTE`` for top-of-book pricing
  (cheaper, suitable for portfolio NAV refresh).

Both modes emit canonical ``MarketBar`` Avro payloads onto the
``market.bar.v1`` topic with ``bar_type='alphavantage_realtime'`` /
``'alphavantage_quote'`` so the silver-tier transform can branch
cleanly.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterable
from typing import Any

from aqp.config import settings
from aqp.streaming.ingesters.base import BaseIngester, IngesterMetrics
from aqp.streaming.kafka_producer import KafkaAvroProducer

logger = logging.getLogger(__name__)


_BASE_URL = "https://www.alphavantage.co/query"


def _ticker_to_vt(symbol: str) -> str:
    """Map an Alpha Vantage equity symbol onto the AQP vt_symbol convention."""
    return f"{symbol}.NASDAQ"


def _ns_now() -> int:
    return time.time_ns()


class AlphaVantageIngester(BaseIngester):
    """REST-poll Alpha Vantage and republish onto Kafka.

    Implements the same :class:`BaseIngester` contract as the
    existing IBKR / Alpaca ingesters so the
    :class:`aqp.streaming.producers.supervisor.ProducerSupervisor`
    can start / stop / scale it identically.
    """

    venue = "alphavantage"

    def __init__(
        self,
        producer: KafkaAvroProducer,
        *,
        universe: Iterable[str] | None = None,
        api_key: str | None = None,
        mode: str = "intraday",
        interval: str = "1min",
        request_interval_seconds: float = 12.0,
    ) -> None:
        super().__init__(
            producer,
            universe=list(universe or settings.stream_universe_list),
            metrics=IngesterMetrics(venue=self.venue),
        )
        self.api_key = api_key or self._resolve_api_key()
        self.mode = str(mode)
        if self.mode not in {"intraday", "quote"}:
            raise ValueError(f"AlphaVantageIngester: unknown mode {mode!r}")
        self.interval = str(interval)
        self.request_interval_seconds = max(float(request_interval_seconds), 1.0)
        if not self.api_key:
            raise ValueError(
                "AlphaVantageIngester requires an API key. Set "
                "AQP_ALPHAVANTAGE_API_KEY or pass api_key=... explicitly. "
                "Free tier: https://www.alphavantage.co/support/#api-key"
            )

    def _resolve_api_key(self) -> str | None:
        for attr in (
            "alphavantage_api_key",
            "alpha_vantage_api_key",
            "av_api_key",
        ):
            value = getattr(settings, attr, None)
            if value:
                return str(value)
        return None

    async def _run_once(self) -> None:
        """Single sweep across the universe — base class drives the outer loop."""
        try:
            import httpx
        except Exception as exc:
            raise ImportError(
                "AlphaVantageIngester requires httpx. Install with: pip install httpx"
            ) from exc

        async with httpx.AsyncClient(timeout=20.0) as client:
            for ticker in self.universe:
                if not self._running:
                    break
                params = self._build_params(ticker)
                try:
                    response = await client.get(_BASE_URL, params=params)
                    response.raise_for_status()
                    payload = response.json()
                except Exception:
                    logger.exception(
                        "AlphaVantageIngester: request failed for ticker=%s mode=%s",
                        ticker,
                        self.mode,
                    )
                    self.metrics.record_error("request_failed")
                    await asyncio.sleep(self.request_interval_seconds)
                    continue
                events = self._parse_payload(ticker, payload)
                for event in events:
                    try:
                        self.producer.publish_bar(**event)
                        self.metrics.record_message("market.bar.v1")
                    except Exception:
                        logger.exception(
                            "AlphaVantageIngester: producer publish failed for %s", ticker
                        )
                        self.metrics.record_error("publish_failed")
                await asyncio.sleep(self.request_interval_seconds)

    # ------------------------------------------------------------------ helpers

    def _build_params(self, ticker: str) -> dict[str, str]:
        if self.mode == "quote":
            return {
                "function": "GLOBAL_QUOTE",
                "symbol": ticker,
                "apikey": self.api_key or "",
            }
        return {
            "function": "TIME_SERIES_INTRADAY",
            "symbol": ticker,
            "interval": self.interval,
            "apikey": self.api_key or "",
            "outputsize": "compact",
        }

    def _parse_payload(self, ticker: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not isinstance(payload, dict):
            return out
        if self.mode == "intraday":
            series_key = next(
                (k for k in payload if "Time Series" in str(k)),
                None,
            )
            if series_key is None:
                return out
            series = payload.get(series_key) or {}
            for ts_str, bar in series.items():
                if not isinstance(bar, dict):
                    continue
                try:
                    out.append(
                        {
                            "vt_symbol": _ticker_to_vt(ticker),
                            "timestamp_ns": _ns_from_iso(ts_str),
                            "open": float(bar["1. open"]),
                            "high": float(bar["2. high"]),
                            "low": float(bar["3. low"]),
                            "close": float(bar["4. close"]),
                            "volume": float(bar["5. volume"]),
                            "bar_type": "alphavantage_realtime",
                        }
                    )
                except (KeyError, TypeError, ValueError):
                    continue
            return out
        if self.mode == "quote":
            quote = payload.get("Global Quote") or {}
            try:
                out.append(
                    {
                        "vt_symbol": _ticker_to_vt(ticker),
                        "timestamp_ns": _ns_now(),
                        "open": float(quote["02. open"]),
                        "high": float(quote["03. high"]),
                        "low": float(quote["04. low"]),
                        "close": float(quote["05. price"]),
                        "volume": float(quote["06. volume"]),
                        "bar_type": "alphavantage_quote",
                    }
                )
            except (KeyError, TypeError, ValueError):
                pass
            return out
        return out


def _ns_from_iso(ts_str: str) -> int:
    from datetime import datetime as _dt

    try:
        return int(_dt.fromisoformat(ts_str).timestamp() * 1_000_000_000)
    except Exception:
        return _ns_now()


__all__ = ["AlphaVantageIngester"]
