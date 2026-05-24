"""Producer application entrypoint.

Pattern borrowed from aqp's ``KafkaAvroProducer`` (BaseIngester supervises a
producer loop; here we expose ``ProducerApp`` with a single-shot
``publish`` method so subclasses can inherit or instantiate directly).
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from confluent_kafka import KafkaError, Producer
from opentelemetry import trace
from prometheus_client import Counter, Histogram, start_http_server

from .avro_codec import AvroCodec
from .config import ProducerSettings
from .tracing import configure_tracing, instrument_kafka_confluent

logger = logging.getLogger(__name__)

MESSAGES_PUBLISHED = Counter(
    "kafka_producer_messages_published_total",
    "Kafka messages produced.",
    ["topic", "status"],
)
PUBLISH_LATENCY = Histogram(
    "kafka_producer_publish_seconds",
    "Latency of the produce+poll loop.",
    ["topic"],
    buckets=(0.001, 0.005, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)
DEADLETTER = Counter(
    "kafka_producer_deadletter_total",
    "Messages pushed to the dead-letter topic.",
    ["reason"],
)


def _kafka_config(settings: ProducerSettings) -> Dict[str, Any]:
    cfg: Dict[str, Any] = {
        "bootstrap.servers": settings.bootstrap_servers,
        "security.protocol": settings.security_protocol,
        "sasl.mechanism": settings.sasl_mechanism,
        "sasl.username": settings.sasl_username,
        "enable.idempotence": True,
        "acks": "all",
        "compression.type": "snappy",
        "linger.ms": 10,
    }
    if settings.sasl_password:
        cfg["sasl.password"] = settings.sasl_password
    if settings.ssl_ca_location:
        cfg["ssl.ca.location"] = settings.ssl_ca_location
    return cfg


def build_producer(settings: ProducerSettings) -> Producer:
    return Producer(_kafka_config(settings))


@dataclass
class ProducerApp:
    settings: ProducerSettings
    codec: AvroCodec
    producer: Producer = field(init=False)
    tracer: trace.Tracer = field(init=False)

    def __post_init__(self) -> None:
        self.tracer = configure_tracing(
            self.settings.service_name, self.settings.otel_endpoint
        )
        instrument_kafka_confluent()
        self.producer = build_producer(self.settings)
        start_http_server(self.settings.metrics_port)

    def publish(
        self,
        record: Dict[str, Any],
        key: Optional[str] = None,
        schema_name: Optional[str] = None,
    ) -> None:
        topic = self.settings.topic
        schema = schema_name or self.settings.schema_name
        labels = {"topic": topic}
        with self.tracer.start_as_current_span(
            "kafka.produce",
            attributes={
                "messaging.system": "kafka",
                "messaging.destination.name": topic,
                "messaging.kafka.schema": schema,
            },
        ):
            started = time.perf_counter()
            try:
                payload = self.codec.encode(schema, record)
                self.producer.produce(
                    topic=topic,
                    key=key.encode() if key else None,
                    value=payload,
                    on_delivery=self._on_delivery,
                )
                self.producer.poll(0)
                MESSAGES_PUBLISHED.labels(status="queued", **labels).inc()
            except Exception as exc:  # noqa: BLE001
                logger.exception("produce failed; sending to deadletter")
                self._send_deadletter(record, reason=type(exc).__name__)
                MESSAGES_PUBLISHED.labels(status="error", **labels).inc()
            finally:
                PUBLISH_LATENCY.labels(**labels).observe(time.perf_counter() - started)

    def flush(self, timeout: float = 10.0) -> None:
        self.producer.flush(timeout)

    def close(self) -> None:
        self.producer.flush(15.0)
        self.codec.close()

    def _send_deadletter(self, record: Dict[str, Any], *, reason: str) -> None:
        try:
            self.producer.produce(
                topic=self.settings.deadletter_topic,
                value=str(record).encode("utf-8"),
                headers={"reason": reason.encode()},
            )
            self.producer.poll(0)
            DEADLETTER.labels(reason=reason).inc()
        except Exception:  # noqa: BLE001
            logger.exception("deadletter publish failed (no retry)")

    @staticmethod
    def _on_delivery(err: Optional[KafkaError], msg: Any) -> None:
        if err is not None:
            logger.error("delivery failed: %s", err)
            MESSAGES_PUBLISHED.labels(topic=msg.topic(), status="delivery_error").inc()
        else:
            MESSAGES_PUBLISHED.labels(topic=msg.topic(), status="delivered").inc()


def run_sample(settings: Optional[ProducerSettings] = None) -> None:
    """Reference loop that produces synthetic ``market.trade.v1`` records."""

    logging.basicConfig(level=logging.INFO)
    cfg = settings or ProducerSettings()
    codec = AvroCodec(cfg.schema_registry_url, group=cfg.schema_group)
    app = ProducerApp(settings=cfg, codec=codec)
    try:
        interval = 1.0 / max(cfg.rate_per_second, 1)
        while True:
            now = time.time_ns()
            record = {
                "ts_ns": now,
                "vt_symbol": random.choice(["AAPL.NASDAQ", "MSFT.NASDAQ", "SPY.NYSE"]),
                "price": round(random.uniform(100.0, 500.0), 2),
                "size": random.randint(1, 100),
                "exchange": "NASDAQ",
                "conditions": [],
                "received_ts_ns": now,
            }
            app.publish(record, key=record["vt_symbol"])
            time.sleep(interval)
    except KeyboardInterrupt:
        logger.info("interrupted, flushing")
    finally:
        app.close()
