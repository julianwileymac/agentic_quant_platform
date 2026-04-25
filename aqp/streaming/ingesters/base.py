"""Base class + metrics helpers for streaming ingesters."""
from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from aqp.streaming.kafka_producer import KafkaAvroProducer

logger = logging.getLogger(__name__)


try:
    from prometheus_client import Counter, Gauge  # type: ignore[import]

    _INGEST_COUNTER = Counter(
        "aqp_stream_ingest_total",
        "Records ingested from upstream venues (pre-Kafka)",
        ["venue", "channel"],
    )
    _RECONNECT_COUNTER = Counter(
        "aqp_stream_reconnect_total",
        "Ingester reconnection attempts",
        ["venue"],
    )
    _CONNECTED_GAUGE = Gauge(
        "aqp_stream_connected",
        "1 if the ingester is currently connected to its upstream venue",
        ["venue"],
    )
except ImportError:  # pragma: no cover
    _INGEST_COUNTER = None
    _RECONNECT_COUNTER = None
    _CONNECTED_GAUGE = None


@dataclass
class IngesterMetrics:
    """Tiny counter bag that doubles as a testing seam."""

    venue: str
    ingested: int = 0
    errors: int = 0

    def record(self, channel: str, count: int = 1) -> None:
        self.ingested += count
        if _INGEST_COUNTER is not None:
            _INGEST_COUNTER.labels(venue=self.venue, channel=channel).inc(count)

    def mark_connected(self, connected: bool) -> None:
        if _CONNECTED_GAUGE is not None:
            _CONNECTED_GAUGE.labels(venue=self.venue).set(1 if connected else 0)

    def mark_reconnect(self) -> None:
        if _RECONNECT_COUNTER is not None:
            _RECONNECT_COUNTER.labels(venue=self.venue).inc()


class BaseIngester(ABC):
    """Common scaffolding for IBKR + Alpaca ingesters.

    Subclasses implement :meth:`_run_once` which consumes the upstream
    venue until it raises. ``run`` wraps it with exponential backoff so the
    process survives IB Gateway daily-resets, Alpaca WSS 1011 closes, etc.
    """

    venue: str = "base"

    def __init__(
        self,
        producer: KafkaAvroProducer,
        *,
        universe: list[str] | None = None,
        metrics: IngesterMetrics | None = None,
    ) -> None:
        self._producer = producer
        self._universe = list(universe or [])
        self._stop_event = asyncio.Event()
        self.metrics = metrics or IngesterMetrics(venue=self.venue)

    @property
    def universe(self) -> list[str]:
        return list(self._universe)

    def stop(self) -> None:
        self._stop_event.set()

    @abstractmethod
    async def _run_once(self) -> None:
        """Connect, subscribe, and consume until cancelled or the link breaks."""

    def produce(self, schema_name: str, record: dict[str, Any], *, channel: str) -> None:
        """Shorthand: stamp ingest_ts_ns, count, and publish to Kafka."""
        record.setdefault("ingest_ts_ns", time.time_ns())
        self._producer.produce_record(schema_name, record)
        self.metrics.record(channel=channel)

    async def run(self, *, max_backoff_sec: float = 60.0) -> None:
        """Main supervisor loop with exponential backoff."""
        backoff = 1.0
        while not self._stop_event.is_set():
            try:
                self.metrics.mark_connected(True)
                await self._run_once()
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - top of the loop
                logger.exception("%s ingester crashed; backing off %.1fs", self.venue, backoff)
                self.metrics.errors += 1
                self.metrics.mark_connected(False)
                self.metrics.mark_reconnect()
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=backoff)
                except asyncio.TimeoutError:
                    pass
                backoff = min(backoff * 2, max_backoff_sec)
                continue
            # Clean exit from _run_once (e.g. test completion).
            break

        self.metrics.mark_connected(False)
