"""``data.redpanda_subscribe`` — bounded Kafka / Redpanda subscribe for a Lab run.

Phase 2 ships an inline bounded subscriber that snapshots up to
``params.max_messages`` messages from the requested topic so the Lab
canvas can wire a "live snapshot" upstream without running a
long-lived Dagster job. Phase 4 promotes this to the Dagster sandbox
where the subscriber runs continuously and emits ``stream.market``
envelopes through the WS bus.

Params:

- ``topic`` (str, required).
- ``cluster`` (str, optional) — selects between Strimzi / Redpanda
  per :mod:`aqp.streaming.clusters` topic routing; ``None`` lets the
  router pick automatically.
- ``group_id`` (str, optional) — defaults to a per-run consumer group
  so the snapshot doesn't interfere with production consumers.
- ``max_messages`` (int, default 200).
- ``timeout_seconds`` (float, default 5.0).
- ``start_from`` (Literal['earliest','latest','timestamp'], default 'latest').
- ``start_timestamp_ms`` (int, optional) — required when
  ``start_from='timestamp'``.

The executor never splits ``vt_symbol`` on ``.`` (rule 1); when the
record carries a ``vt_symbol`` field it's preserved verbatim.
"""
from __future__ import annotations

import logging
import time
from typing import Any
from uuid import uuid4

from aqp.lab.executors._helpers import base_locator, stash_arrow_output
from aqp.lab.executors._types import NodeContext, NodeResult

logger = logging.getLogger(__name__)


def execute(node: Any, ctx: NodeContext) -> NodeResult:
    params = dict(getattr(node, "params", {}) or {})
    topic = str(params.get("topic") or "").strip()
    if not topic:
        return NodeResult(
            status="error",
            error="data.redpanda_subscribe requires params.topic",
            log_label="data.redpanda_subscribe:missing_topic",
        )
    cluster = params.get("cluster")
    group_id = str(params.get("group_id") or f"aqp-lab-{node.id}-{uuid4().hex[:6]}")
    max_messages = int(params.get("max_messages") or 200)
    timeout_seconds = float(params.get("timeout_seconds") or 5.0)
    start_from = str(params.get("start_from") or "latest").lower()
    start_timestamp_ms = params.get("start_timestamp_ms")

    if max_messages <= 0:
        return NodeResult(
            status="error",
            error="data.redpanda_subscribe params.max_messages must be > 0",
            log_label="data.redpanda_subscribe:bad_max",
        )
    if max_messages > 10_000:
        return NodeResult(
            status="error",
            error="data.redpanda_subscribe params.max_messages must be <= 10000 (Phase 2 bound)",
            log_label="data.redpanda_subscribe:over_limit",
        )

    try:
        from aqp.streaming.clusters import cluster_for_topic, get_cluster
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=f"streaming cluster routing unavailable: {exc}",
            log_label="data.redpanda_subscribe:routing_import_fail",
        )
    try:
        from confluent_kafka import Consumer, TopicPartition  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=f"confluent-kafka client not installed: {exc}",
            log_label="data.redpanda_subscribe:no_kafka_client",
        )

    try:
        descriptor = get_cluster(cluster) if cluster else cluster_for_topic(topic)
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=f"could not resolve cluster for topic {topic!r}: {exc}",
            log_label="data.redpanda_subscribe:resolve_fail",
        )

    consumer_cfg = descriptor.producer_config(client_id=f"aqp-lab-sub-{node.id}")
    consumer_cfg.update(
        {
            "group.id": group_id,
            "enable.auto.commit": False,
            "auto.offset.reset": "earliest" if start_from == "earliest" else "latest",
            "session.timeout.ms": 10_000,
        }
    )
    consumer = Consumer(consumer_cfg)
    try:
        consumer.subscribe([topic])
        if start_from == "timestamp" and start_timestamp_ms is not None:
            partitions = consumer.assignment() or _wait_for_assignment(consumer, 1.0)
            offsets = consumer.offsets_for_times(
                [
                    TopicPartition(topic, part.partition, int(start_timestamp_ms))
                    for part in partitions
                    if part.topic == topic
                ]
            )
            consumer.assign(offsets)

        records: list[dict[str, Any]] = []
        deadline = time.monotonic() + timeout_seconds
        while len(records) < max_messages and time.monotonic() < deadline:
            msg = consumer.poll(timeout=min(0.5, max(0.0, deadline - time.monotonic())))
            if msg is None:
                continue
            if msg.error() is not None:
                continue
            value = msg.value()
            try:
                payload = value.decode("utf-8") if isinstance(value, (bytes, bytearray)) else value
            except UnicodeDecodeError:
                payload = repr(value)
            records.append(
                {
                    "topic": msg.topic(),
                    "partition": int(msg.partition()),
                    "offset": int(msg.offset()),
                    "timestamp_ms": int(msg.timestamp()[1]) if msg.timestamp() else None,
                    "key": _maybe_decode(msg.key()),
                    "value": payload,
                }
            )
    finally:
        try:
            consumer.close()
        except Exception:  # noqa: BLE001
            pass

    import pandas as pd

    df = pd.DataFrame.from_records(records) if records else pd.DataFrame(
        columns=["topic", "partition", "offset", "timestamp_ms", "key", "value"]
    )
    stash_arrow_output(ctx, node.id, df)
    return NodeResult(
        status="done",
        output_locator={
            **base_locator(node.id, df, kind="redpanda_subscribe"),
            "topic": topic,
            "cluster": descriptor.name,
            "group_id": group_id,
            "max_messages": max_messages,
            "start_from": start_from,
        },
        metrics={
            "messages_consumed": int(len(records)),
            "timeout_seconds": timeout_seconds,
        },
        log_label=f"data.redpanda_subscribe:{topic}",
    )


def _maybe_decode(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.hex()
    return value


def _wait_for_assignment(consumer: Any, timeout_seconds: float) -> list[Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        assigned = consumer.assignment()
        if assigned:
            return assigned
        consumer.poll(0.1)
    return consumer.assignment() or []


__all__ = ["execute"]
