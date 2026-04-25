"""Redis pub/sub bridge -- the async progress bus between workers and the UI.

The cluster supports two logical channel families on a single Redis
pub/sub connection:

- ``aqp:task:<task_id>``  -- long-running Celery task progress feeds
- ``aqp:live:<channel>`` -- live market-data relays (see
  :mod:`aqp.api.routes.market_data_live`)

Callers select the namespace via the ``namespace`` kwarg (defaults to
``"task"`` to preserve backward compatibility with existing workers).
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


def _channel(task_id: str, namespace: Namespace = "task") -> str:
    if namespace not in ("task", "live"):
        raise ValueError(f"Unknown pub/sub namespace: {namespace!r}")
    return f"aqp:{namespace}:{task_id}"


def publish(task_id: str, payload: dict[str, Any], *, namespace: Namespace = "task") -> None:
    """Synchronous publish -- used by Celery tasks and the live feed loop."""
    import redis

    client = redis.Redis.from_url(settings.redis_pubsub_url, decode_responses=True)
    with tracer.start_as_current_span("ws.publish") as span:
        span.set_attribute("aqp.namespace", namespace)
        span.set_attribute("aqp.channel_id", task_id)
        if isinstance(payload, dict) and payload.get("kind"):
            span.set_attribute("aqp.payload_kind", str(payload.get("kind")))
        try:
            client.publish(_channel(task_id, namespace), json.dumps(payload, default=str))
            logger.debug("pub/sub published namespace=%s channel=%s", namespace, task_id)
        except Exception as exc:
            span.record_exception(exc)
            logger.exception("pub/sub publish failed for %s %s", namespace, task_id)


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
