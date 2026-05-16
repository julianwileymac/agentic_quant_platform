"""OwnershipEvent bus — bridges SQLAlchemy commits to the graph store.

Writes flow:

1. A request commits a tenancy row (e.g. a new ``Membership``).
2. The :mod:`aqp.graph.sqlalchemy_hooks` ``after_flush_postexec``
   listener inspects the flush plan and emits an :class:`OwnershipEvent`
   for each affected row.
3. The event lands on the Redis stream ``aqp:ownership:events`` (or an
   in-process list when Redis isn't reachable — the fallback exists
   so unit tests run hermetically).
4. The :func:`aqp.tasks.ownership_tasks.drain_events` Celery worker
   consumes the stream in batches of
   :attr:`Settings.ownership_sync_batch_size` and applies them via
   :meth:`OwnershipGraphStore.apply_events`.

The drain task is idempotent: events store the full ``OwnershipNode``
/ ``OwnershipEdge`` payload, not just an id, so replaying a batch
converges on the same Neo4j state.
"""
from __future__ import annotations

import enum
import json
import logging
import threading
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from aqp.config import settings
from aqp.graph.protocol import OwnershipEdge, OwnershipNode

logger = logging.getLogger(__name__)


_STREAM_KEY: str = "aqp:ownership:events"


class OwnershipEventKind(str, enum.Enum):
    UPSERT_NODE = "upsert_node"
    UPSERT_EDGE = "upsert_edge"
    DELETE_NODE = "delete_node"
    DELETE_EDGE = "delete_edge"


@dataclass
class OwnershipEvent:
    kind: OwnershipEventKind
    node: OwnershipNode | None = None
    edge: OwnershipEdge | None = None
    source: str = "sqlalchemy"
    emitted_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_payload(self) -> dict[str, Any]:
        """Serialise for Redis stream storage."""
        payload: dict[str, Any] = {
            "kind": self.kind.value,
            "source": self.source,
            "emitted_at": self.emitted_at,
        }
        if self.node is not None:
            payload["node"] = asdict(self.node)
        if self.edge is not None:
            payload["edge"] = asdict(self.edge)
        return payload

    @classmethod
    def from_payload(cls, raw: dict[str, Any]) -> "OwnershipEvent":
        node_dict = raw.get("node")
        edge_dict = raw.get("edge")
        node = OwnershipNode(**node_dict) if isinstance(node_dict, dict) else None
        edge = OwnershipEdge(**edge_dict) if isinstance(edge_dict, dict) else None
        return cls(
            kind=OwnershipEventKind(raw.get("kind", "upsert_node")),
            node=node,
            edge=edge,
            source=str(raw.get("source") or "sqlalchemy"),
            emitted_at=str(raw.get("emitted_at") or datetime.utcnow().isoformat()),
        )


# ---------------------------------------------------------------------------
# In-process fallback when Redis is unavailable
# ---------------------------------------------------------------------------

_FALLBACK_LOCK = threading.Lock()
_FALLBACK_QUEUE: list[OwnershipEvent] = []


def _redis_client() -> Any | None:
    """Return a redis client or ``None`` when Redis is unavailable."""
    try:
        import redis  # type: ignore[import-not-found]
    except Exception:  # pragma: no cover - dep guard
        return None
    try:
        client = redis.Redis.from_url(
            settings.redis_pubsub_url or settings.redis_url,
            decode_responses=True,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
        )
        client.ping()
        return client
    except Exception:  # noqa: BLE001
        return None


def emit_ownership_event(event: OwnershipEvent) -> None:
    """Push an event onto the stream (Redis if reachable, in-memory otherwise).

    Best-effort: never raises. If both Redis and the in-memory fallback
    fail, the event is dropped and a warning is logged — the periodic
    :func:`aqp.tasks.ownership_tasks.full_resync` healer recovers from
    any such loss.
    """
    payload = event.to_payload()
    body = json.dumps(payload, default=str)
    client = _redis_client()
    if client is not None:
        try:
            # Streams keep insertion order and let multiple workers
            # cooperate via consumer groups when scaled out.
            client.xadd(_STREAM_KEY, {"payload": body})
            return
        except Exception:  # noqa: BLE001
            logger.debug("ownership event emit to redis failed", exc_info=True)
    with _FALLBACK_LOCK:
        _FALLBACK_QUEUE.append(event)


def iter_drained_events(*, max_events: int = 1000) -> Iterable[OwnershipEvent]:
    """Drain up to *max_events* events from the stream (or the fallback).

    Each call removes the events it returns. Designed for the Celery
    drain task; tests can drive the in-memory fallback by interleaving
    :func:`emit_ownership_event` calls with this generator.
    """
    yielded = 0
    client = _redis_client()
    if client is not None:
        try:
            # XRANGE + XDEL is simpler than consumer groups for our
            # single-writer drain. If the queue grows we can switch to
            # consumer groups without changing the producer contract.
            items = client.xrange(_STREAM_KEY, count=max_events)
            for entry_id, fields in items or []:
                raw = fields.get("payload") if isinstance(fields, dict) else None
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                yield OwnershipEvent.from_payload(payload)
                yielded += 1
                if yielded >= max_events:
                    break
            if items:
                client.xdel(_STREAM_KEY, *(entry_id for entry_id, _ in items))
        except Exception:  # noqa: BLE001
            logger.debug("ownership drain via redis failed; falling back", exc_info=True)

    # Always also drain the in-process fallback so events emitted while
    # Redis was down get applied as soon as it comes back.
    with _FALLBACK_LOCK:
        local = _FALLBACK_QUEUE[:max_events - yielded] if max_events > yielded else []
        if local:
            del _FALLBACK_QUEUE[: len(local)]
    for ev in local:
        yield ev


def reset_fallback_queue_for_tests() -> None:
    """Test helper — drops the in-memory queue."""
    with _FALLBACK_LOCK:
        _FALLBACK_QUEUE.clear()


__all__ = [
    "OwnershipEvent",
    "OwnershipEventKind",
    "emit_ownership_event",
    "iter_drained_events",
    "reset_fallback_queue_for_tests",
]
