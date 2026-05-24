"""Shared Kafka producer for the AQP streaming pipeline.

Thin wrapper over ``confluent_kafka.Producer`` that:

- Serializes records with the canonical Avro schemas from
  :mod:`aqp.streaming.schemas`.
- Keys every record by ``vt_symbol`` so Kafka partitioning preserves
  per-symbol ordering end-to-end.
- Emits Prometheus counters/histograms for rate + latency + errors.
- Applies the ``AQP_KAFKA_TOPIC_PREFIX`` prefix consistently.
- Routes persistent delivery failures onto ``market.deadletter.v1``.

Phase 2a of the AQP infra-expansion plan added optional side-by-side
routing between Strimzi Kafka and Redpanda. Pass ``cluster="redpanda"``
to :class:`KafkaAvroProducer` to target Redpanda explicitly. When the
``cluster`` kwarg is omitted, the producer falls back to the legacy
``settings.kafka_*`` values (Strimzi). The :func:`produce_record`
method also auto-routes per-record by topic-name prefix:
``market.l1.*`` / ``market.l2.*`` / ``execution.orders.*`` /
``agentic.state.*`` go to Redpanda; everything else stays on Strimzi.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from aqp.config import settings
from aqp.streaming.clusters import (
    StreamingCluster,
    cluster_for_topic,
    get_cluster,
)
from aqp.streaming.schemas import (
    SCHEMA_BY_TOPIC,
    TOPIC_BY_SCHEMA,
    avro_encode,
    topic_for,
)

logger = logging.getLogger(__name__)

DEADLETTER_TOPIC = "market.deadletter.v1"


try:  # Prometheus metrics are optional -- the producer runs without them.
    from prometheus_client import Counter, Histogram  # type: ignore[import]

    _PRODUCE_COUNTER = Counter(
        "aqp_stream_produce_total",
        "Kafka records produced by the AQP streaming ingester",
        ["topic", "venue_source", "result"],
    )
    _PRODUCE_LATENCY = Histogram(
        "aqp_stream_produce_latency_seconds",
        "End-to-end produce latency (ingest->ack)",
        ["topic"],
        buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
    )
    _DEADLETTER_COUNTER = Counter(
        "aqp_stream_deadletter_total",
        "Records routed to the deadletter topic after retry exhaustion",
        ["origin_topic"],
    )
except ImportError:  # pragma: no cover
    _PRODUCE_COUNTER = None
    _PRODUCE_LATENCY = None
    _DEADLETTER_COUNTER = None


class KafkaAvroProducer:
    """Long-lived producer that encodes Avro records and tracks metrics.

    The underlying ``confluent_kafka.Producer`` is thread-safe; call
    :meth:`produce` from any thread and :meth:`flush` on shutdown. We also
    service delivery callbacks opportunistically on each ``produce`` call
    by pumping ``poll(0)``.
    """

    def __init__(
        self,
        bootstrap: str | None = None,
        client_id: str | None = None,
        *,
        topic_prefix: str | None = None,
        extra_config: dict[str, Any] | None = None,
        cluster: str | StreamingCluster | None = None,
        auto_route: bool = False,
    ) -> None:
        try:
            from confluent_kafka import Producer  # type: ignore[import]
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                'KafkaAvroProducer requires the "streaming" extra. '
                'Install with: pip install -e ".[streaming]"'
            ) from exc

        if isinstance(cluster, StreamingCluster):
            self._cluster = cluster
        elif cluster:
            self._cluster = get_cluster(cluster)
        else:
            self._cluster = None

        self._auto_route = bool(auto_route)
        # Per-cluster cached delegate producers when auto_route=True.
        self._sibling_producers: dict[str, "KafkaAvroProducer"] = {}

        # Bootstrap precedence: explicit ctor arg > cluster descriptor > legacy
        # settings.kafka_bootstrap. Same for client_id.
        if self._cluster is not None:
            self.bootstrap = bootstrap or self._cluster.bootstrap
            self.client_id = client_id or f"aqp-{self._cluster.name}"
        else:
            self.bootstrap = bootstrap or settings.kafka_bootstrap
            self.client_id = client_id or settings.kafka_client_id
        self.topic_prefix = topic_prefix if topic_prefix is not None else settings.kafka_topic_prefix

        cfg: dict[str, Any] = {
            "bootstrap.servers": self.bootstrap,
            "client.id": self.client_id,
            "compression.type": settings.kafka_compression,
            "acks": settings.kafka_acks,
            "enable.idempotence": True,
            "linger.ms": 10,
            "batch.size": 65536,
            "queue.buffering.max.messages": 200_000,
            "queue.buffering.max.kbytes": 524_288,
            "message.max.bytes": 10_485_760,
        }
        # Pull security from the cluster descriptor if set; otherwise legacy.
        if self._cluster is not None:
            sec = self._cluster.security_protocol
            mech = self._cluster.sasl_mechanism
            user = self._cluster.sasl_username
            password = self._cluster.sasl_password
        else:
            sec = settings.kafka_security_protocol
            mech = settings.kafka_sasl_mechanism
            user = settings.kafka_sasl_username
            password = settings.kafka_sasl_password
        if sec and sec != "PLAINTEXT":
            cfg["security.protocol"] = sec
        if mech:
            cfg["sasl.mechanism"] = mech
        if user:
            cfg["sasl.username"] = user
        if password:
            cfg["sasl.password"] = password
        if extra_config:
            cfg.update(extra_config)

        self._producer = Producer(cfg)
        self._pending_starts: dict[int, float] = {}

    @property
    def cluster_name(self) -> str:
        """Return the cluster alias this producer targets (default: strimzi)."""
        if self._cluster is not None:
            return self._cluster.name
        return "strimzi"

    def _topic(self, name: str) -> str:
        if not self.topic_prefix:
            return name
        return f"{self.topic_prefix}{name}"

    def produce_record(
        self,
        schema_name: str,
        record: dict[str, Any],
        *,
        key: str | None = None,
    ) -> None:
        """Serialize and enqueue a record for the schema's canonical topic.

        ``key`` defaults to ``record["vt_symbol"]`` so downstream consumers
        see per-symbol ordering; pass an explicit key (or ``""``) to opt out.

        When ``auto_route=True`` was passed to the constructor, the topic
        name is matched against :data:`aqp.streaming.clusters.TOPIC_PREFIX_ROUTES`
        and the call delegates to a per-cluster sibling producer when the
        match diverges from this producer's cluster.
        """
        topic = self._topic(topic_for(schema_name))
        if self._auto_route:
            target_cluster = cluster_for_topic(topic)
            if target_cluster.name != self.cluster_name:
                self._delegate(target_cluster).produce_record(
                    schema_name, record, key=key
                )
                return
        venue_source = str(record.get("venue_source", "unknown"))
        effective_key = (
            key if key is not None else str(record.get("vt_symbol", ""))
        )
        try:
            payload = avro_encode(schema_name, record)
        except Exception:
            logger.exception(
                "avro encode failed for schema=%s topic=%s vt_symbol=%s",
                schema_name,
                topic,
                record.get("vt_symbol"),
            )
            if _PRODUCE_COUNTER is not None:
                _PRODUCE_COUNTER.labels(topic=topic, venue_source=venue_source, result="encode_error").inc()
            return

        start = time.perf_counter()

        def _on_delivery(err: Any, msg: Any) -> None:
            elapsed = time.perf_counter() - start
            if err is not None:
                logger.warning(
                    "kafka delivery failed topic=%s key=%s err=%s",
                    topic,
                    effective_key,
                    err,
                )
                self._send_deadletter(topic, payload, str(err))
                if _PRODUCE_COUNTER is not None:
                    _PRODUCE_COUNTER.labels(topic=topic, venue_source=venue_source, result="failed").inc()
                return
            if _PRODUCE_COUNTER is not None:
                _PRODUCE_COUNTER.labels(topic=topic, venue_source=venue_source, result="ok").inc()
            if _PRODUCE_LATENCY is not None:
                _PRODUCE_LATENCY.labels(topic=topic).observe(elapsed)

        try:
            self._producer.produce(
                topic=topic,
                key=effective_key or None,
                value=payload,
                on_delivery=_on_delivery,
            )
        except BufferError:
            # Local queue full: block briefly, then retry once.
            self._producer.poll(0.5)
            self._producer.produce(
                topic=topic,
                key=effective_key or None,
                value=payload,
                on_delivery=_on_delivery,
            )
        # Service callbacks without blocking; upstream loops stay hot.
        self._producer.poll(0)

    def _send_deadletter(self, origin_topic: str, payload: bytes, reason: str) -> None:
        dlq = self._topic(DEADLETTER_TOPIC)
        try:
            self._producer.produce(
                topic=dlq,
                key=origin_topic,
                value=payload,
                headers=[("origin_topic", origin_topic.encode()), ("reason", reason.encode())],
            )
            if _DEADLETTER_COUNTER is not None:
                _DEADLETTER_COUNTER.labels(origin_topic=origin_topic).inc()
        except Exception:
            logger.exception("deadletter produce failed for %s", origin_topic)

    def _delegate(self, target: StreamingCluster) -> "KafkaAvroProducer":
        """Lazily build a sibling producer for ``target`` (auto-route mode)."""
        if target.name in self._sibling_producers:
            return self._sibling_producers[target.name]
        sibling = KafkaAvroProducer(
            cluster=target,
            topic_prefix=self.topic_prefix,
            auto_route=False,
        )
        self._sibling_producers[target.name] = sibling
        return sibling

    def flush(self, timeout: float = 10.0) -> None:
        """Block until every queued record has been delivered or timed out."""
        remaining = self._producer.flush(timeout)
        if remaining > 0:
            logger.warning("kafka flush timed out with %d records still pending", remaining)
        for sibling in self._sibling_producers.values():
            try:
                sibling.flush(timeout)
            except Exception:  # noqa: BLE001
                logger.warning("sibling cluster flush failed", exc_info=True)

    def close(self) -> None:
        """Flush and drop the producer. Safe to call multiple times."""
        try:
            self.flush()
        except Exception:
            logger.exception("kafka flush raised on close")
        for sibling in self._sibling_producers.values():
            try:
                sibling.close()
            except Exception:  # noqa: BLE001
                logger.warning("sibling cluster close failed", exc_info=True)


def topic_names(prefix: str | None = None) -> list[str]:
    """Return the resolved list of canonical topic names (with prefix applied)."""
    effective = prefix if prefix is not None else settings.kafka_topic_prefix
    return [f"{effective}{t}" for t in TOPIC_BY_SCHEMA.values()] + [f"{effective}{DEADLETTER_TOPIC}"]


def schema_for(topic: str) -> str:
    """Reverse lookup used by consumers (strips prefix when needed)."""
    if settings.kafka_topic_prefix and topic.startswith(settings.kafka_topic_prefix):
        topic = topic[len(settings.kafka_topic_prefix) :]
    return SCHEMA_BY_TOPIC[topic]


__all__ = [
    "DEADLETTER_TOPIC",
    "KafkaAvroProducer",
    "schema_for",
    "topic_names",
]
