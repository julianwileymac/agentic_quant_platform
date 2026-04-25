"""Alpaca market-data ingester -> Kafka.

Covers every channel from the Alpaca real-time stock data WebSocket:

- ``trades``       -> ``market.trade.v1``
- ``quotes``       -> ``market.quote.v1``
- ``bars``         -> ``market.bar.v1`` (bar_type=realtime)
- ``updatedBars``  -> ``market.bar.v1`` (bar_type=updated)
- ``dailyBars``    -> ``market.bar.v1`` (bar_type=daily)
- ``statuses``     -> ``market.status.v1``
- ``imbalances``   -> ``market.imbalance.v1``
- ``corrections``  -> ``market.correction.v1`` (correction_kind=correction)
- ``cancelErrors`` -> ``market.correction.v1`` (correction_kind=cancel|error)

Feed tier comes from ``AQP_ALPACA_FEED`` (``iex`` default, ``sip``, or
``delayed_sip``). The ingester respects ``AQP_STREAM_INCLUDE_*`` toggles
so lightweight deployments can drop high-volume channels.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterable
from typing import Any

try:
    from alpaca.data.live.stock import StockDataStream  # type: ignore[import]
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        'AlpacaIngester requires the "alpaca" extra. '
        'Install with: pip install -e ".[alpaca]"'
    ) from exc

from aqp.config import settings
from aqp.streaming.ingesters.base import BaseIngester, IngesterMetrics
from aqp.streaming.kafka_producer import KafkaAvroProducer

logger = logging.getLogger(__name__)


def _ns_from_ts(ts: Any) -> int:
    if ts is None:
        return time.time_ns()
    try:
        return int(ts.timestamp() * 1_000_000_000)
    except Exception:
        return time.time_ns()


def _ticker_to_vt(symbol: Any, feed: str) -> str:
    # Alpaca exposes US equities; we pin the exchange dimension to NASDAQ for
    # vt_symbol parity with the existing AlpacaDataFeed.
    return f"{symbol}.NASDAQ"


class AlpacaIngester(BaseIngester):
    venue = "alpaca"

    def __init__(
        self,
        producer: KafkaAvroProducer,
        *,
        universe: Iterable[str] | None = None,
        api_key: str | None = None,
        secret_key: str | None = None,
        feed: str | None = None,
    ) -> None:
        super().__init__(
            producer,
            universe=list(universe or settings.stream_universe_list),
            metrics=IngesterMetrics(venue=self.venue),
        )
        self.api_key = api_key or settings.alpaca_api_key
        self.secret_key = secret_key or settings.alpaca_secret_key
        self.feed = feed or settings.alpaca_feed
        if not (self.api_key and self.secret_key):
            raise ValueError(
                "AlpacaIngester requires AQP_ALPACA_API_KEY + AQP_ALPACA_SECRET_KEY"
            )
        self._stream: StockDataStream | None = None

    async def _run_once(self) -> None:
        self._stream = StockDataStream(
            self.api_key,
            self.secret_key,
            feed=self.feed,
        )
        symbols = [s.split(".")[0] if "." in s else s for s in self.universe]
        if not symbols:
            raise RuntimeError("AlpacaIngester started with empty universe")

        if settings.stream_include_trades:
            self._stream.subscribe_trades(self._on_trade, *symbols)
            self._stream.subscribe_trade_corrections(self._on_correction, *symbols)
            self._stream.subscribe_trade_cancel_errors(self._on_cancel_error, *symbols)
        if settings.stream_include_quotes:
            self._stream.subscribe_quotes(self._on_quote, *symbols)
        if settings.stream_include_bars:
            self._stream.subscribe_bars(self._on_bar, *symbols)
            self._stream.subscribe_updated_bars(self._on_updated_bar, *symbols)
            self._stream.subscribe_daily_bars(self._on_daily_bar, *symbols)
        self._stream.subscribe_statuses(self._on_status, *symbols)
        try:
            self._stream.subscribe_imbalances(self._on_imbalance, *symbols)
        except AttributeError:
            # Older alpaca-py versions lack imbalance support -- continue without it.
            logger.warning("alpaca-py does not expose subscribe_imbalances(); skipping")

        logger.info(
            "alpaca ingester connected feed=%s symbols=%d",
            self.feed,
            len(symbols),
        )

        runner = asyncio.create_task(self._stream._run_forever(), name="alpaca-ws")  # noqa: SLF001
        try:
            while not self._stop_event.is_set() and not runner.done():
                await asyncio.sleep(1.0)
            if runner.done():
                # Re-raise if the WebSocket task died so ``run`` backs off.
                exc = runner.exception()
                if exc is not None:
                    raise exc
        finally:
            runner.cancel()
            try:
                await runner
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            try:
                await self._stream.stop_ws()
            except Exception:
                logger.exception("alpaca stop_ws failed")
            self._stream = None

    # -----------------------------------------------------------------
    # Channel handlers -- each converts the alpaca-py model to a dict
    # matching the corresponding Avro schema and forwards to Kafka.
    # -----------------------------------------------------------------

    async def _on_trade(self, msg: Any) -> None:
        try:
            self.produce(
                "market_trade_v1",
                {
                    "ts_ns": _ns_from_ts(getattr(msg, "timestamp", None)),
                    "vt_symbol": _ticker_to_vt(msg.symbol, self.feed),
                    "price": float(msg.price),
                    "size": float(getattr(msg, "size", 0.0) or 0.0),
                    "exchange_code": str(getattr(msg, "exchange", "")) or None,
                    "conditions": [str(c) for c in (getattr(msg, "conditions", None) or [])],
                    "trade_id": str(getattr(msg, "id", "")) or None,
                    "venue_source": "alpaca",
                },
                channel="trade",
            )
        except Exception:
            logger.exception("alpaca trade handler failed")

    async def _on_quote(self, msg: Any) -> None:
        try:
            self.produce(
                "market_quote_v1",
                {
                    "ts_ns": _ns_from_ts(getattr(msg, "timestamp", None)),
                    "vt_symbol": _ticker_to_vt(msg.symbol, self.feed),
                    "bid": float(getattr(msg, "bid_price", 0.0) or 0.0),
                    "ask": float(getattr(msg, "ask_price", 0.0) or 0.0),
                    "bid_size": float(getattr(msg, "bid_size", 0) or 0),
                    "ask_size": float(getattr(msg, "ask_size", 0) or 0),
                    "bid_exchange": str(getattr(msg, "bid_exchange", "")) or None,
                    "ask_exchange": str(getattr(msg, "ask_exchange", "")) or None,
                    "conditions": [str(c) for c in (getattr(msg, "conditions", None) or [])],
                    "venue_source": "alpaca",
                },
                channel="quote",
            )
        except Exception:
            logger.exception("alpaca quote handler failed")

    async def _on_bar(self, msg: Any) -> None:
        await self._emit_bar(msg, bar_type="realtime", interval="1m", channel="bar")

    async def _on_updated_bar(self, msg: Any) -> None:
        await self._emit_bar(msg, bar_type="updated", interval="1m", channel="updated_bar")

    async def _on_daily_bar(self, msg: Any) -> None:
        await self._emit_bar(msg, bar_type="daily", interval="1d", channel="daily_bar")

    async def _emit_bar(self, msg: Any, *, bar_type: str, interval: str, channel: str) -> None:
        try:
            self.produce(
                "market_bar_v1",
                {
                    "ts_ns": _ns_from_ts(getattr(msg, "timestamp", None)),
                    "vt_symbol": _ticker_to_vt(msg.symbol, self.feed),
                    "interval": interval,
                    "open": float(msg.open),
                    "high": float(msg.high),
                    "low": float(msg.low),
                    "close": float(msg.close),
                    "volume": float(msg.volume),
                    "vwap": float(getattr(msg, "vwap", 0.0)) or None,
                    "trade_count": int(getattr(msg, "trade_count", 0)) or None,
                    "bar_type": bar_type,
                    "venue_source": "alpaca",
                },
                channel=channel,
            )
        except Exception:
            logger.exception("alpaca bar handler failed (%s)", channel)

    async def _on_status(self, msg: Any) -> None:
        try:
            self.produce(
                "market_status_v1",
                {
                    "ts_ns": _ns_from_ts(getattr(msg, "timestamp", None)),
                    "vt_symbol": _ticker_to_vt(msg.symbol, self.feed),
                    "status_code": str(getattr(msg, "status_code", "")) or "",
                    "reason": getattr(msg, "reason", None) or None,
                    "tape": getattr(msg, "tape", None) or None,
                    "venue_source": "alpaca",
                },
                channel="status",
            )
        except Exception:
            logger.exception("alpaca status handler failed")

    async def _on_imbalance(self, msg: Any) -> None:
        try:
            self.produce(
                "market_imbalance_v1",
                {
                    "ts_ns": _ns_from_ts(getattr(msg, "timestamp", None)),
                    "vt_symbol": _ticker_to_vt(msg.symbol, self.feed),
                    "aggregate_imbalance": float(getattr(msg, "aggregate_imbalance", 0.0)) or None,
                    "auction_price": float(getattr(msg, "auction_price", 0.0)) or None,
                    "current_reference_price": float(getattr(msg, "current_reference_price", 0.0)) or None,
                    "indicative_match_price": float(getattr(msg, "indicative_match_price", 0.0)) or None,
                    "imbalance_side": getattr(msg, "imbalance_side", None),
                    "venue_source": "alpaca",
                },
                channel="imbalance",
            )
        except Exception:
            logger.exception("alpaca imbalance handler failed")

    async def _on_correction(self, msg: Any) -> None:
        try:
            self.produce(
                "market_correction_v1",
                {
                    "ts_ns": _ns_from_ts(getattr(msg, "timestamp", None)),
                    "vt_symbol": _ticker_to_vt(msg.symbol, self.feed),
                    "correction_kind": "correction",
                    "original_trade_id": str(getattr(msg, "original_id", "")) or None,
                    "original_exchange": str(getattr(msg, "original_exchange", "")) or None,
                    "original_price": float(getattr(msg, "original_price", 0.0) or 0.0),
                    "original_size": float(getattr(msg, "original_size", 0.0) or 0.0),
                    "original_conditions": [str(c) for c in (getattr(msg, "original_conditions", None) or [])],
                    "corrected_trade_id": str(getattr(msg, "corrected_id", "")) or None,
                    "corrected_price": float(getattr(msg, "corrected_price", 0.0) or 0.0),
                    "corrected_size": float(getattr(msg, "corrected_size", 0.0) or 0.0),
                    "corrected_conditions": [str(c) for c in (getattr(msg, "corrected_conditions", None) or [])],
                    "venue_source": "alpaca",
                },
                channel="correction",
            )
        except Exception:
            logger.exception("alpaca correction handler failed")

    async def _on_cancel_error(self, msg: Any) -> None:
        try:
            # alpaca-py exposes both cancel and error on the same channel.
            kind = "cancel" if getattr(msg, "action", "cancel") == "cancel" else "error"
            self.produce(
                "market_correction_v1",
                {
                    "ts_ns": _ns_from_ts(getattr(msg, "timestamp", None)),
                    "vt_symbol": _ticker_to_vt(msg.symbol, self.feed),
                    "correction_kind": kind,
                    "original_trade_id": str(getattr(msg, "id", "")) or None,
                    "original_exchange": str(getattr(msg, "exchange", "")) or None,
                    "original_price": float(getattr(msg, "price", 0.0) or 0.0),
                    "original_size": float(getattr(msg, "size", 0.0) or 0.0),
                    "original_conditions": [],
                    "corrected_trade_id": None,
                    "corrected_price": None,
                    "corrected_size": None,
                    "corrected_conditions": [],
                    "venue_source": "alpaca",
                },
                channel="cancel_error",
            )
        except Exception:
            logger.exception("alpaca cancel/error handler failed")
