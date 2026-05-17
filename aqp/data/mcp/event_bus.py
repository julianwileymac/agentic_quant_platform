from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FeedEvent:
    """Event payload emitted when feed configuration changes."""

    kind: str
    data_source_id: str
    payload: dict[str, Any] = field(default_factory=dict)


class FeedEventBus:
    """In-process pub/sub for feed configuration changes.

    The MCP server subscribes to this bus to refresh the per-feed tool
    catalog without restart. Handlers run synchronously on the publisher's
    thread; long-running callbacks should offload work.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._handlers: list[Callable[[FeedEvent], None]] = []

    def subscribe(self, handler: Callable[[FeedEvent], None]) -> Callable[[], None]:
        """Register a handler and return an unsubscribe callback."""

        with self._lock:
            self._handlers.append(handler)

        def _unsubscribe() -> None:
            with self._lock:
                try:
                    self._handlers.remove(handler)
                except ValueError:
                    return

        return _unsubscribe

    def publish(self, event: FeedEvent) -> None:
        """Fan-out one event to every registered handler."""

        with self._lock:
            handlers = list(self._handlers)
        for handler in handlers:
            try:
                handler(event)
            except Exception:  # noqa: BLE001
                logger.exception("FeedEventBus handler raised; continuing")


_BUS: FeedEventBus | None = None
_BUS_LOCK = threading.Lock()


def get_feed_event_bus() -> FeedEventBus:
    """Return the process singleton event bus."""

    global _BUS
    if _BUS is None:
        with _BUS_LOCK:
            if _BUS is None:
                _BUS = FeedEventBus()
    return _BUS


def publish_feed_event(
    *,
    kind: str,
    data_source_id: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Publish one feed event onto the singleton bus."""

    get_feed_event_bus().publish(
        FeedEvent(kind=kind, data_source_id=data_source_id, payload=payload or {})
    )


__all__ = ["FeedEvent", "FeedEventBus", "get_feed_event_bus", "publish_feed_event"]
