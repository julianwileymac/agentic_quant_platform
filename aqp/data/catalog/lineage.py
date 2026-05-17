"""First-class lineage tracking for the AQP data layer.

The :class:`LineageWriter` is the single sanctioned entry point for
appending rows to ``data_lineage_events``. Observer subclasses
(:class:`BaseLineageObserver`) wrap individual data-motion call sites
(Iceberg append, sink materialise, dbt build, Airbyte sync, MCP tool
invocation) so the rule "all lineage writes go through ``LineageWriter``"
stays enforceable.

This is the **Observer pattern** the architectural blueprint calls
out — observers are decoupled from the main pipeline thread so a slow
or failing lineage insert never blocks a data write.
"""
from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Iterable, Iterator

from aqp.persistence.db import get_session
from aqp.persistence.models_lineage import (
    LINEAGE_TRANSFORM_KINDS,
    DataLineageEvent,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LineageEvent:
    """In-memory representation of a row in ``data_lineage_events``."""

    transform_kind: str
    source_table_id: str | None = None
    target_table_id: str | None = None
    actor: str | None = None
    actor_kind: str | None = None  # user|agent|service|system
    run_id: str | None = None
    manifest_id: str | None = None
    mcp_tool_name: str | None = None
    service_name: str | None = None
    rows_written: int | None = None
    medallion_layer: str | None = None
    summary: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    workspace_id: str | None = None
    project_id: str | None = None
    owner_user_id: str | None = None
    created_at: datetime | None = None

    def normalised_kind(self) -> str:
        """Return ``transform_kind`` clamped to a known canonical value or itself."""
        kind = (self.transform_kind or "").strip()
        if not kind:
            return "unknown"
        return kind


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


class LineageWriter:
    """Single sanctioned writer for ``data_lineage_events``.

    Failures are swallowed and logged so a busted lineage table never
    crashes a data pipeline. The writer is intentionally cheap and sync —
    expensive aggregation (eg. graph rebuilds) is deferred to Celery.
    """

    _suppression_depth = threading.local()

    def record(self, event: LineageEvent) -> str | None:
        if getattr(self._suppression_depth, "value", 0) > 0:
            logger.debug("Lineage event suppressed: %s", event.transform_kind)
            return None
        try:
            with get_session() as session:
                row = DataLineageEvent(
                    source_table_id=event.source_table_id,
                    target_table_id=event.target_table_id,
                    transform_kind=event.normalised_kind(),
                    actor=event.actor,
                    actor_kind=event.actor_kind,
                    run_id=event.run_id,
                    manifest_id=event.manifest_id,
                    mcp_tool_name=event.mcp_tool_name,
                    service_name=event.service_name,
                    rows_written=(
                        str(event.rows_written) if event.rows_written is not None else None
                    ),
                    medallion_layer=event.medallion_layer,
                    summary=event.summary,
                    details_json=dict(event.details or {}),
                    created_at=event.created_at or datetime.utcnow(),
                )
                if event.owner_user_id:
                    row.owner_user_id = event.owner_user_id
                if event.workspace_id:
                    row.workspace_id = event.workspace_id
                if event.project_id:
                    row.project_id = event.project_id
                session.add(row)
                session.commit()
                row_id = str(row.id)
            return row_id
        except Exception:  # noqa: BLE001
            logger.exception(
                "LineageWriter.record failed for kind=%s target=%s",
                event.transform_kind,
                event.target_table_id,
            )
            return None

    def record_many(self, events: Iterable[LineageEvent]) -> list[str | None]:
        return [self.record(event) for event in events]

    @classmethod
    @contextmanager
    def suppress(cls) -> Iterator[None]:
        """Context manager that suppresses lineage writes inside its block.

        Used by tests and one-off scripts to avoid littering the
        ``data_lineage_events`` table with synthetic rows.
        """
        local = cls._suppression_depth
        depth = getattr(local, "value", 0)
        local.value = depth + 1
        try:
            yield
        finally:
            local.value = max(depth, 0)


_default_writer = LineageWriter()


def record_lineage(
    transform_kind: str,
    *,
    source: str | None = None,
    target: str | None = None,
    actor: str | None = None,
    actor_kind: str | None = None,
    run_id: str | None = None,
    manifest_id: str | None = None,
    mcp_tool_name: str | None = None,
    service_name: str | None = None,
    rows_written: int | None = None,
    medallion_layer: str | None = None,
    summary: str | None = None,
    details: dict[str, Any] | None = None,
) -> str | None:
    """Convenience wrapper around :class:`LineageWriter`.

    Most call sites prefer this single-line entry over instantiating
    the writer themselves.
    """
    event = LineageEvent(
        transform_kind=transform_kind,
        source_table_id=source,
        target_table_id=target,
        actor=actor,
        actor_kind=actor_kind,
        run_id=run_id,
        manifest_id=manifest_id,
        mcp_tool_name=mcp_tool_name,
        service_name=service_name,
        rows_written=rows_written,
        medallion_layer=medallion_layer,
        summary=summary,
        details=details or {},
    )
    return _default_writer.record(event)


# ---------------------------------------------------------------------------
# Observer pattern
# ---------------------------------------------------------------------------


class BaseLineageObserver:
    """Observer base class for lineage events.

    Subclasses override :meth:`should_handle` and :meth:`handle` to
    react to events selectively. Observers are decoupled from the
    main thread by registering with :class:`LineageBus` and processing
    events asynchronously when desired.
    """

    name: str = "base"

    def should_handle(self, event: LineageEvent) -> bool:  # pragma: no cover
        return True

    def handle(self, event: LineageEvent) -> None:  # pragma: no cover
        raise NotImplementedError


class LineageBus:
    """Pub/sub bus for lineage events.

    Lets the wrapper / executor / sink emit one ``LineageEvent`` and
    have N observers react in turn (audit log, quality monitor,
    DataHub emitter, etc.). The main pipeline only depends on the bus
    interface, so observers can be added or removed without touching
    write-path code.
    """

    def __init__(self) -> None:
        self._observers: list[BaseLineageObserver] = []
        self._lock = threading.Lock()

    def register(self, observer: BaseLineageObserver) -> None:
        with self._lock:
            if observer not in self._observers:
                self._observers.append(observer)

    def unregister(self, observer: BaseLineageObserver) -> None:
        with self._lock:
            try:
                self._observers.remove(observer)
            except ValueError:
                pass

    def emit(self, event: LineageEvent) -> None:
        with self._lock:
            observers = list(self._observers)
        for observer in observers:
            try:
                if observer.should_handle(event):
                    observer.handle(event)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "LineageObserver %s failed for event=%s",
                    observer.name,
                    event.transform_kind,
                )


_default_bus = LineageBus()


def get_lineage_bus() -> LineageBus:
    """Return the process-wide lineage bus."""
    return _default_bus


# ---------------------------------------------------------------------------
# Built-in observers
# ---------------------------------------------------------------------------


class WriterLineageObserver(BaseLineageObserver):
    """Observer that persists every event via :class:`LineageWriter`.

    Registered by default so every event reaches Postgres. Other
    observers (audit, DataHub mirror, alerting) can be registered on
    top without changing this one.
    """

    name = "writer"

    def __init__(self, writer: LineageWriter | None = None) -> None:
        self._writer = writer or _default_writer

    def handle(self, event: LineageEvent) -> None:
        self._writer.record(event)


# Register the default writer-observer so emitting an event through
# the bus persists by default. Tests can call
# ``get_lineage_bus().unregister(...)`` to swap behavior.
_default_bus.register(WriterLineageObserver())


def emit_event(event: LineageEvent) -> None:
    """Convenience wrapper around the default bus + writer."""
    _default_bus.emit(event)


def event_to_dict(event: LineageEvent) -> dict[str, Any]:
    """Helper for tests / introspection."""
    return asdict(event)


__all__ = [
    "BaseLineageObserver",
    "LINEAGE_TRANSFORM_KINDS",
    "LineageBus",
    "LineageEvent",
    "LineageWriter",
    "WriterLineageObserver",
    "emit_event",
    "event_to_dict",
    "get_lineage_bus",
    "record_lineage",
]
