"""Redis pub/sub bridge + bounded replay stream — the progress bus.

The cluster supports two logical channel families on a single Redis
pub/sub connection:

- ``aqp:task:<task_id>``  -- long-running Celery task progress feeds
- ``aqp:live:<channel>`` -- live market-data relays (see
  :mod:`aqp.api.routes.market_data_live`)

In addition, every progress frame is **dual-written** to a bounded
Redis Stream at ``aqp:task:frames:<task_id>`` so a WebSocket client
that reconnects can replay frames it missed during the disconnect
window. The stream is capped via ``XADD ... MAXLEN ~ <cap>`` and
expired by :func:`prune_replay_stream` (called from the worker's
``after_task_run`` signal) so memory is bounded.

Callers select the namespace via the ``namespace`` kwarg (defaults
to ``"task"`` to preserve backward compatibility with existing
workers). Only the ``task`` namespace persists to the replay stream
— live market data is too high-volume to durably buffer.
"""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Iterator
from typing import Any, Literal

from aqp.config import settings
from aqp.observability import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer("aqp.ws")

Namespace = Literal["task", "live"]

# Replay-stream bounds. The MAXLEN bound is approximate (Redis uses
# ``~`` to trim with a more efficient algorithm) and the TTL cleans
# up streams for tasks that completed long ago. Override via
# settings: ``AQP_TASK_REPLAY_MAXLEN`` / ``AQP_TASK_REPLAY_TTL``.
_REPLAY_KEY_PREFIX = "aqp:task:frames:"
_REPLAY_DEFAULT_MAXLEN = 10_000
_REPLAY_DEFAULT_TTL_SECONDS = 60 * 60 * 24  # 24h


def _channel(task_id: str, namespace: Namespace = "task") -> str:
    if namespace not in ("task", "live"):
        raise ValueError(f"Unknown pub/sub namespace: {namespace!r}")
    return f"aqp:{namespace}:{task_id}"


def _replay_key(task_id: str) -> str:
    return f"{_REPLAY_KEY_PREFIX}{task_id}"


def _replay_maxlen() -> int:
    raw = getattr(settings, "task_replay_maxlen", None)
    try:
        value = int(raw) if raw is not None else _REPLAY_DEFAULT_MAXLEN
    except (TypeError, ValueError):
        value = _REPLAY_DEFAULT_MAXLEN
    return max(100, value)


def _replay_ttl_seconds() -> int:
    raw = getattr(settings, "task_replay_ttl_seconds", None)
    try:
        value = int(raw) if raw is not None else _REPLAY_DEFAULT_TTL_SECONDS
    except (TypeError, ValueError):
        value = _REPLAY_DEFAULT_TTL_SECONDS
    return max(60, value)


def publish(task_id: str, payload: dict[str, Any], *, namespace: Namespace = "task") -> None:
    """Synchronous publish + bounded stream append (task namespace only).

    AGENTS rule 4: the frame shape
    ``{task_id, stage, message, timestamp, **extras}`` is contract.
    The stream stores the frame as a single ``data`` field carrying
    the JSON body so future extensions don't require an XADD field
    migration.
    """
    import redis

    client = redis.Redis.from_url(settings.redis_pubsub_url, decode_responses=True)
    serialized = json.dumps(payload, default=str)
    with tracer.start_as_current_span("ws.publish") as span:
        span.set_attribute("aqp.namespace", namespace)
        span.set_attribute("aqp.channel_id", task_id)
        if isinstance(payload, dict) and payload.get("kind"):
            span.set_attribute("aqp.payload_kind", str(payload.get("kind")))
        try:
            client.publish(_channel(task_id, namespace), serialized)
            logger.debug("pub/sub published namespace=%s channel=%s", namespace, task_id)
            if namespace == "task":
                # Approximate MAXLEN trim is much cheaper than exact.
                try:
                    client.xadd(
                        _replay_key(task_id),
                        {"data": serialized},
                        maxlen=_replay_maxlen(),
                        approximate=True,
                    )
                    client.expire(_replay_key(task_id), _replay_ttl_seconds())
                except Exception:
                    # The stream is best-effort: a Redis hiccup must
                    # never break pub/sub delivery. Log + continue.
                    logger.exception(
                        "replay stream xadd failed for task %s", task_id
                    )
        except Exception as exc:
            span.record_exception(exc)
            logger.exception("pub/sub publish failed for %s %s", namespace, task_id)


def replay_frames(
    task_id: str,
    *,
    since: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Read replay-stream frames for ``task_id``.

    ``since`` is the inclusive-exclusive Redis Stream id of the last
    frame the client already saw — pass ``"-"`` (or omit) for "from
    the beginning of the buffered window". ``limit`` is clamped to
    ``[1, 10_000]`` so a malicious caller can't blow up the worker.

    Returns a list of ``{frame_id, ...payload}`` dicts in stream
    order. ``frame_id`` is the Redis Stream id (e.g.
    ``"1716640123456-0"``) which the client persists so the next
    reconnect resumes after this exact frame.
    """
    import redis

    bounded_limit = max(1, min(int(limit), 10_000))
    start = "-"
    if since:
        # Redis XRANGE start is inclusive; bump the offset by 1ms to
        # make it exclusive of the last-seen id without losing later
        # frames produced in the same millisecond.
        try:
            ms_str, seq_str = since.split("-", 1)
            start = f"{int(ms_str)}-{int(seq_str) + 1}"
        except ValueError:
            start = since
    client = redis.Redis.from_url(settings.redis_pubsub_url, decode_responses=True)
    out: list[dict[str, Any]] = []
    try:
        entries = client.xrange(
            _replay_key(task_id), min=start, max="+", count=bounded_limit
        )
    except Exception:
        logger.exception("replay stream xrange failed for task %s", task_id)
        return out
    for entry_id, fields in entries:
        raw = fields.get("data") if isinstance(fields, dict) else None
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"raw": raw}
        if isinstance(payload, dict):
            payload["frame_id"] = entry_id
            out.append(payload)
    return out


def prune_replay_stream(task_id: str) -> None:
    """Delete the replay stream for a completed task.

    Called by Celery's ``after_task_run`` signal once the operator
    UI has had a grace window to consume the final ``done`` /
    ``error`` frame. Failure is silently ignored — the TTL set on
    every ``xadd`` is the eventual cleanup floor.
    """
    import redis

    client = redis.Redis.from_url(settings.redis_pubsub_url, decode_responses=True)
    try:
        client.delete(_replay_key(task_id))
    except Exception:  # pragma: no cover
        logger.debug("replay stream prune ignored for task %s", task_id)


def subscribe(task_id: str, *, namespace: Namespace = "task") -> Iterator[dict[str, Any]]:
    """Synchronous iterator -- handy for scripts and CLI progress bars."""
    import redis

    client = redis.Redis.from_url(settings.redis_pubsub_url, decode_responses=True)
    pubsub = client.pubsub()
    pubsub.subscribe(_channel(task_id, namespace))
    for message in pubsub.listen():
        if message.get("type") != "message":
            continue
        try:
            yield json.loads(message["data"])
        except Exception:  # pragma: no cover
            yield {"raw": message["data"]}


async def asubscribe(task_id: str, *, namespace: Namespace = "task") -> AsyncIterator[dict[str, Any]]:
    """Async iterator -- used by FastAPI WebSocket routes."""
    import redis.asyncio as aioredis

    client = aioredis.from_url(settings.redis_pubsub_url, decode_responses=True)
    pubsub = client.pubsub()
    with tracer.start_as_current_span("ws.asubscribe") as span:
        span.set_attribute("aqp.namespace", namespace)
        span.set_attribute("aqp.channel_id", task_id)
        await pubsub.subscribe(_channel(task_id, namespace))
        logger.info("pub/sub subscribed namespace=%s channel=%s", namespace, task_id)
        first_message = True
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                if first_message:
                    first_message = False
                    span.add_event("ws.first_message")
                    logger.info("pub/sub first message namespace=%s channel=%s", namespace, task_id)
                try:
                    yield json.loads(message["data"])
                except Exception:
                    yield {"raw": message["data"]}
        except Exception as exc:
            span.record_exception(exc)
            logger.exception("pub/sub subscribe loop failed namespace=%s channel=%s", namespace, task_id)
            raise
        finally:
            await pubsub.unsubscribe(_channel(task_id, namespace))
            await pubsub.close()
            await client.close()
            logger.info("pub/sub unsubscribed namespace=%s channel=%s", namespace, task_id)
