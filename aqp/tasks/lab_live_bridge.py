"""Per-session Kafka / Redpanda bridge for the Lab WebSocket.

Phase 5 — long-lived Celery task that subscribes to a curated set of
Redpanda topics (selected via ``GET /streams/topics``) and
republishes throttled events onto the Lab WS multiplex
(``/ws/lab/{session_id}``) as ``stream.market`` / ``stream.fill`` /
``stream.pnl`` envelopes.

Frame shape preserves AGENTS rule 4 — ``{task_id, stage, message,
timestamp, **extras}`` — so the WS pump forwards the envelopes
through the existing :func:`aqp.tasks._progress.emit` path. Each
Lab session gets its own ``task_id`` so multiple operators on the
same lab don't collide.

The worker honours the kill-switch via the
``aqp:lab:halt:<run_id>`` Redis flag (same key the inline canvas /
per-node dispatcher polls) so a global halt-all kills the live
bridge too.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Iterable

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="aqp.tasks.lab_live_bridge.bridge_session")
def bridge_session(
    self,
    session_id: str,
    *,
    topics: list[str],
    cluster: str | None = None,
    duration_seconds: float = 60.0,
    tick_budget: int = 10_000,
    throttle_hz: float = 30.0,
) -> dict[str, Any]:
    """Subscribe to ``topics`` and republish onto ``/ws/lab/{session_id}``.

    The task self-terminates after ``duration_seconds`` OR when the
    per-session halt flag at ``aqp:lab:halt:<session_id>`` is set.

    ``tick_budget`` caps total envelopes (the bridge stops once it's
    forwarded that many) so a chatty topic can't unbounded-grow the
    WS ring. ``throttle_hz`` sleeps between batches so a fast topic
    is downsampled to the operator's frontend frame budget (the
    aqp_client throttle is already 30 FPS by default — matching).
    """
    task_id = self.request.id or f"lab-bridge:{session_id}"
    emit(
        task_id,
        "queued",
        f"lab live bridge queued for {len(topics)} topics",
        session_id=session_id,
        topics=topics,
    )

    if not topics:
        emit_error(task_id, "no topics specified", session_id=session_id)
        return {"status": "error", "error": "no topics", "session_id": session_id}

    try:
        from aqp.streaming.clusters import cluster_for_topic, get_cluster
    except Exception as exc:  # noqa: BLE001
        emit_error(task_id, f"streaming cluster registry import failed: {exc}")
        return {"status": "error", "error": str(exc), "session_id": session_id}
    try:
        from confluent_kafka import Consumer  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        emit_error(task_id, f"confluent-kafka client not installed: {exc}")
        return {"status": "error", "error": str(exc), "session_id": session_id}

    descriptor = (
        get_cluster(cluster) if cluster else cluster_for_topic(topics[0])
    )
    consumer_cfg = descriptor.producer_config(client_id=f"lab-bridge:{session_id}")
    consumer_cfg.update(
        {
            "group.id": f"lab-bridge:{session_id}",
            "enable.auto.commit": False,
            "auto.offset.reset": "latest",
            "session.timeout.ms": 10_000,
        }
    )
    consumer = Consumer(consumer_cfg)

    # Halt-flag client — best effort; the bridge keeps running when
    # Redis is unreachable.
    halt_client = None
    try:
        from aqp.config import settings

        import redis  # type: ignore[import-not-found]

        halt_client = redis.Redis.from_url(
            getattr(settings, "redis_url", None), socket_timeout=0.25
        )
    except Exception:  # noqa: BLE001
        halt_client = None

    consumer.subscribe(list(topics))
    forwarded = 0
    started = time.monotonic()
    period = 1.0 / max(0.1, throttle_hz)
    last_emit = 0.0
    try:
        while True:
            if time.monotonic() - started >= duration_seconds:
                break
            if forwarded >= tick_budget:
                break
            if halt_client is not None:
                try:
                    if halt_client.get(f"aqp:lab:halt:{session_id}"):
                        emit(
                            task_id,
                            "halted",
                            f"lab live bridge halted by aqp:lab:halt:{session_id}",
                            session_id=session_id,
                        )
                        break
                except Exception:  # noqa: BLE001
                    pass
            msg = consumer.poll(timeout=min(0.5, max(0.0, period * 4)))
            if msg is None:
                continue
            if msg.error() is not None:
                continue
            now = time.monotonic()
            if now - last_emit < period:
                continue
            last_emit = now
            payload = _decode_payload(msg.value())
            topic = msg.topic()
            kind = _classify_envelope_kind(topic)
            extras: dict[str, Any] = {
                "topic": topic,
                "partition": int(msg.partition()),
                "offset": int(msg.offset()),
                "payload": payload,
                "session_id": session_id,
            }
            ts_pair = msg.timestamp() or (0, 0)
            extras["origin_ts_ms"] = int(ts_pair[1]) if isinstance(ts_pair, tuple) else 0
            emit(task_id, kind, f"{kind}: {topic}", **extras)
            forwarded += 1
    except Exception as exc:  # noqa: BLE001
        logger.exception("lab live bridge crashed")
        emit_error(task_id, f"lab live bridge crashed: {exc}", session_id=session_id)
        try:
            consumer.close()
        except Exception:  # noqa: BLE001
            pass
        return {"status": "error", "error": str(exc), "session_id": session_id}

    try:
        consumer.close()
    except Exception:  # noqa: BLE001
        pass
    result = {
        "status": "done",
        "session_id": session_id,
        "topics": list(topics),
        "forwarded": forwarded,
        "duration_seconds": time.monotonic() - started,
    }
    emit_done(task_id, result)
    return result


def _classify_envelope_kind(topic: str) -> str:
    """Map a Kafka topic name onto a Lab WS envelope kind.

    Convention (matches :mod:`aqp.streaming.clusters` topic routes):

    - ``market.*`` → ``stream.market``
    - ``execution.orders.*`` / ``execution.fills.*`` → ``stream.fill``
    - ``execution.pnl.*`` → ``stream.pnl``
    - everything else → ``stream.market`` (generic catch-all)
    """
    bare = topic.lower()
    if bare.startswith("execution.fills") or bare.startswith("execution.orders"):
        return "stream.fill"
    if bare.startswith("execution.pnl") or bare.startswith("position.pnl"):
        return "stream.pnl"
    return "stream.market"


def _decode_payload(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.hex()
    return value


def _resolve_topics_from_cluster(topic_prefix: str, cluster: str | None = None) -> Iterable[str]:
    """Helper for the REST route — enumerate topics matching a prefix."""
    try:
        from aqp.streaming.admin.kafka_admin import NativeKafkaAdmin

        admin = NativeKafkaAdmin(cluster=cluster)
        return [t for t in admin.list_topics() if t.startswith(topic_prefix)]
    except Exception:  # noqa: BLE001
        return []


__all__ = ["bridge_session"]
