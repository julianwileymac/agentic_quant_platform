"""``LiveStreamingRLDataPipeline`` — Kafka / Flink hybrid for live RL.

Subscribes to the AQP streaming layer (Kafka topic / Flink session-job
output) to collect a rolling window of bars, then exposes them through
the :class:`BaseDataPipeline` contract just like the historic pipelines.

This is the bridge between AQP's streaming admin
(:mod:`aqp.streaming.admin`) and the RL runtime — paper-trading agents
consume the same bar layout as offline-trained policies.
"""
from __future__ import annotations

import logging
import time
from typing import Any, ClassVar

import pandas as pd

from aqp_rl.core.data import BaseDataPipeline

logger = logging.getLogger(__name__)


class LiveStreamingRLDataPipeline(BaseDataPipeline):
    """Kafka-subscribed live bar pipeline (placeholder default)."""

    rl_alias: ClassVar[str] = "LiveStreamingRLDataPipeline"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "streaming"
    rl_tags: ClassVar[tuple[str, ...]] = ("kafka", "flink", "live")

    def __init__(
        self,
        *,
        topic: str = "aqp.bars.1m",
        bootstrap: str | None = None,
        group_id: str = "aqp-rl-live",
        max_history_bars: int = 5000,
        timeout_ms: int = 5000,
        name: str | None = None,
    ) -> None:
        super().__init__(name=name)
        self.topic = str(topic)
        self.bootstrap = bootstrap
        self.group_id = str(group_id)
        self.max_history_bars = int(max_history_bars)
        self.timeout_ms = int(timeout_ms)
        self._buffer: list[dict[str, Any]] = []
        self._consumer: Any = None

    def _ensure_consumer(self) -> None:
        if self._consumer is not None:
            return
        try:
            from aqp.config import settings
            from confluent_kafka import Consumer
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "LiveStreamingRLDataPipeline requires confluent-kafka. "
                "Install with `pip install confluent-kafka`."
            ) from exc
        bootstrap = self.bootstrap or getattr(settings, "kafka_bootstrap", "localhost:9092")
        config = {
            "bootstrap.servers": bootstrap,
            "group.id": self.group_id,
            "auto.offset.reset": "latest",
        }
        self._consumer = Consumer(config)
        self._consumer.subscribe([self.topic])

    def download_data(
        self,
        ticker_list: list[str],
        start: str,
        end: str,
        time_interval: str = "1m",
    ) -> pd.DataFrame:
        """Drain the buffer + new messages into a long-format frame.

        ``start`` / ``end`` are advisory — the live pipeline returns the
        most recent ``max_history_bars`` records that match
        ``ticker_list``. Use :class:`IcebergRLDataPipeline` for backfill.
        """
        self._ensure_consumer()
        deadline = time.time() + (self.timeout_ms / 1000.0)
        while time.time() < deadline:
            msg = self._consumer.poll(0.1)
            if msg is None:
                continue
            if msg.error():
                logger.debug("kafka error: %s", msg.error())
                continue
            try:
                import json as _json

                payload = _json.loads(msg.value().decode("utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if payload.get("tic") in ticker_list:
                self._buffer.append(payload)
                if len(self._buffer) > self.max_history_bars:
                    self._buffer = self._buffer[-self.max_history_bars :]
        if not self._buffer:
            return pd.DataFrame(columns=["date", "tic", "open", "high", "low", "close", "volume"])
        df = pd.DataFrame(self._buffer)
        df["date"] = pd.to_datetime(df.get("date", df.get("timestamp", pd.NaT)))
        return df.sort_values(["date", "tic"], ignore_index=True)


__all__ = ["LiveStreamingRLDataPipeline"]
