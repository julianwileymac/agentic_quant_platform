"""Stream-based fetchers: Kafka, WebSocket."""
from __future__ import annotations

from aqp.data.fetchers.stream.kafka_fetcher import KafkaFetcher
from aqp.data.fetchers.stream.websocket_fetcher import WebSocketFetcher

__all__ = [
    "KafkaFetcher",
    "WebSocketFetcher",
]
