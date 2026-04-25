"""Kafka-backed live data feed.

The ingesters in :mod:`aqp.streaming.ingesters` publish canonical Avro
records to Kafka, and Flink jobs on the ``rpi_kubernetes`` cluster emit
derived topics (``features.normalized.v1``, ``features.signals.v1``).
``KafkaDataFeed`` closes the loop by letting strategies, the paper
trader, and the ``/live`` route consume those records as first-class
AQP domain objects.

Supported ``emit_as`` modes:

- ``bar``    -> yields :class:`aqp.core.types.BarData` from
  ``market.bar.v1``, ``features.indicators.v1``, or
  ``features.normalized.v1`` (close reconstructed).
- ``quote``  -> yields :class:`aqp.core.types.QuoteBar` from
  ``market.quote.v1``.
- ``tick``   -> yields :class:`aqp.core.types.TickData` from
  ``market.trade.v1`` / ``market.quote.v1``.
- ``signal`` -> yields :class:`aqp.core.types.Signal` from
  ``features.signals.v1``.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Iterable
from datetime import datetime, timezone
from typing import Any, Literal

try:
    from aiokafka import AIOKafkaConsumer  # type: ignore[import]
except ImportError as exc:  # pragma: no cover - optional
    raise ImportError(
        'KafkaDataFeed requires the "streaming" extra. '
        'Install with: pip install -e ".[streaming]"'
    ) from exc

from aqp.config import settings
from aqp.core.registry import register
from aqp.core.types import BarData, Direction, Exchange, Interval, QuoteBar, Signal, Symbol, TickData, TickType
from aqp.streaming.schemas import avro_decode, schema_for_topic, topic_for
from aqp.trading.feeds.base import BaseFeed

logger = logging.getLogger(__name__)

EmitAs = Literal["bar", "quote", "tick", "signal"]


def _ns_to_dt(ns: int | None) -> datetime:
    if not ns:
        return datetime.now(timezone.utc)
    return datetime.fromtimestamp(ns / 1_000_000_000, tz=timezone.utc)


def _parse_vt(vt: str) -> Symbol:
    if "." not in vt:
        return Symbol(ticker=vt, exchange=Exchange.NASDAQ)
    ticker, exch = vt.rsplit(".", 1)
    try:
        exchange = Exchange(exch)
    except ValueError:
        exchange = Exchange.NASDAQ
    return Symbol(ticker=ticker, exchange=exchange)


def _interval_of(raw: str | None) -> Interval:
    if not raw:
        return Interval.MINUTE
    try:
        return Interval(raw)
    except ValueError:
        mapping = {"5s": Interval.TEN_SECOND, "30s": Interval.MINUTE}
        return mapping.get(raw, Interval.MINUTE)


_DEFAULT_TOPIC_BY_MODE: dict[EmitAs, str] = {
    "bar": topic_for("features_normalized_v1"),
    "quote": topic_for("market_quote_v1"),
    "tick": topic_for("market_trade_v1"),
    "signal": topic_for("features_signals_v1"),
}


@register("KafkaDataFeed")
class KafkaDataFeed(BaseFeed):
    """Consume processed Flink output (or raw broker events) from Kafka."""

    name = "kafka-feed"

    def __init__(
        self,
        topic: str | None = None,
        *,
        bootstrap: str | None = None,
        group_id: str | None = None,
        emit_as: EmitAs = "bar",
        auto_offset_reset: str = "latest",
    ) -> None:
        super().__init__()
        self.emit_as: EmitAs = emit_as
        self.topic = topic or _DEFAULT_TOPIC_BY_MODE[emit_as]
        if settings.kafka_topic_prefix:
            self.topic = f"{settings.kafka_topic_prefix}{self.topic}"
        self.bootstrap = bootstrap or settings.kafka_bootstrap
        self.group_id = group_id or f"{settings.kafka_consumer_group}-{emit_as}"
        self.auto_offset_reset = auto_offset_reset
        self._consumer: AIOKafkaConsumer | None = None

    async def connect(self) -> None:
        if self._consumer is not None:
            return
        extra: dict[str, Any] = {
            "bootstrap_servers": self.bootstrap,
            "group_id": self.group_id,
            "enable_auto_commit": True,
            "auto_offset_reset": self.auto_offset_reset,
            "value_deserializer": lambda v: v,  # keep raw bytes; decode per message
            "key_deserializer": lambda v: (v.decode("utf-8") if v else None),
        }
        if settings.kafka_security_protocol and settings.kafka_security_protocol != "PLAINTEXT":
            extra["security_protocol"] = settings.kafka_security_protocol
        if settings.kafka_sasl_mechanism:
            extra["sasl_mechanism"] = settings.kafka_sasl_mechanism
            extra["sasl_plain_username"] = settings.kafka_sasl_username
            extra["sasl_plain_password"] = settings.kafka_sasl_password

        self._consumer = AIOKafkaConsumer(self.topic, **extra)
        await self._consumer.start()
        logger.info("KafkaDataFeed started topic=%s group=%s", self.topic, self.group_id)

    async def disconnect(self) -> None:
        if self._consumer is None:
            return
        try:
            await self._consumer.stop()
        finally:
            self._consumer = None

    async def subscribe(self, symbols: Iterable[Symbol]) -> None:
        # Kafka partitioning handles routing; we filter yielded messages by
        # the declared subscription set so strategies can narrow the stream.
        await super().subscribe(symbols)

    async def stream(self) -> AsyncIterator[Any]:
        if self._consumer is None:
            await self.connect()
        assert self._consumer is not None
        try:
            schema_name = schema_for_topic(self.topic)
        except KeyError:
            # Unknown topic -> consumer still runs but we surface raw dicts.
            schema_name = ""

        want = self._subscriptions
        while True:
            try:
                msg = await self._consumer.getone()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("kafka consumer error on topic=%s", self.topic)
                await asyncio.sleep(1.0)
                continue

            try:
                record = avro_decode(schema_name, msg.value) if schema_name else msg.value
            except Exception:
                logger.exception("avro decode failed for topic=%s", self.topic)
                continue
            if not isinstance(record, dict):
                continue

            vt = str(record.get("vt_symbol", ""))
            if want and vt not in want:
                continue

            produced = self._materialize(record)
            if produced is not None:
                yield produced

    # -----------------------------------------------------------------
    # Avro record -> AQP core type
    # -----------------------------------------------------------------

    def _materialize(self, record: dict[str, Any]) -> BarData | QuoteBar | TickData | Signal | None:
        if self.emit_as == "bar":
            return self._to_bar(record)
        if self.emit_as == "quote":
            return self._to_quote(record)
        if self.emit_as == "tick":
            return self._to_tick(record)
        if self.emit_as == "signal":
            return self._to_signal(record)
        return None

    def _to_bar(self, record: dict[str, Any]) -> BarData | None:
        # Accept both raw ``market.bar.v1`` and processed indicator/normalized
        # records -- the latter carry a ``close`` alongside the feature vector.
        close = record.get("close") or record.get("raw_close")
        if close is None:
            return None
        ts = _ns_to_dt(record.get("ts_ns"))
        interval = _interval_of(record.get("interval"))
        return BarData(
            symbol=_parse_vt(record["vt_symbol"]),
            timestamp=ts,
            open=float(record.get("open", close)),
            high=float(record.get("high", close)),
            low=float(record.get("low", close)),
            close=float(close),
            volume=float(record.get("volume", 0.0) or 0.0),
            interval=interval,
            extra={
                k: v
                for k, v in record.items()
                if k
                not in {
                    "ts_ns",
                    "vt_symbol",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "interval",
                    "ingest_ts_ns",
                    "compute_ts_ns",
                }
            },
        )

    def _to_quote(self, record: dict[str, Any]) -> QuoteBar:
        bid = float(record.get("bid", 0.0) or 0.0)
        ask = float(record.get("ask", 0.0) or 0.0)
        return QuoteBar(
            symbol=_parse_vt(record["vt_symbol"]),
            timestamp=_ns_to_dt(record.get("ts_ns")),
            bid_open=bid,
            bid_high=bid,
            bid_low=bid,
            bid_close=bid,
            ask_open=ask,
            ask_high=ask,
            ask_low=ask,
            ask_close=ask,
            bid_size=float(record.get("bid_size", 0.0) or 0.0),
            ask_size=float(record.get("ask_size", 0.0) or 0.0),
            interval=Interval.TICK,
        )

    def _to_tick(self, record: dict[str, Any]) -> TickData:
        if "price" in record:
            price = float(record["price"])
            bid = ask = price
            bid_size = ask_size = float(record.get("size", 0.0) or 0.0)
            tick_type = TickType.TRADE
        else:
            bid = float(record.get("bid", 0.0) or 0.0)
            ask = float(record.get("ask", 0.0) or 0.0)
            price = (bid + ask) / 2 if (bid and ask) else bid or ask
            bid_size = float(record.get("bid_size", 0.0) or 0.0)
            ask_size = float(record.get("ask_size", 0.0) or 0.0)
            tick_type = TickType.QUOTE
        return TickData(
            symbol=_parse_vt(record["vt_symbol"]),
            timestamp=_ns_to_dt(record.get("ts_ns")),
            bid=bid,
            ask=ask,
            last=price,
            volume=float(record.get("size", 0.0) or 0.0),
            bid_size=bid_size,
            ask_size=ask_size,
            tick_type=tick_type,
        )

    def _to_signal(self, record: dict[str, Any]) -> Signal:
        direction_raw = str(record.get("direction", "neutral")).lower()
        direction = {
            "long": Direction.LONG,
            "short": Direction.SHORT,
            "neutral": Direction.NET,
        }.get(direction_raw, Direction.NET)
        horizon_sec = int(record.get("horizon_sec", 86400))
        horizon_days = max(1, horizon_sec // 86400)
        return Signal(
            symbol=_parse_vt(record["vt_symbol"]),
            strength=float(record.get("strength", 0.0)),
            direction=direction,
            timestamp=_ns_to_dt(record.get("ts_ns")),
            confidence=float(record.get("confidence", 1.0)),
            horizon_days=horizon_days,
            source=str(record.get("source_job", "kafka-feed")),
            rationale=record.get("rationale"),
        )


__all__ = ["KafkaDataFeed"]
