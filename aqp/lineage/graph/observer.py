"""LineageBus observer that dual-writes into the bipartite graph (Workstream A).

The legacy :class:`aqp.data.catalog.lineage.WriterLineageObserver`
keeps writing the flat ``data_lineage_events`` edge log. The
:class:`BipartiteGraphObserver` defined below additionally translates
every :class:`LineageEvent` into the matching
``(dataset_vertex, transform_vertex, edges)`` tuple and persists it via
:class:`LineageGraphWriter`.

Registration is idempotent and feature-flagged: the observer attaches
itself only when ``AQP_LINEAGE_GRAPH_ENABLED=true``. Tests that
exercise the flat log unaffected can leave the flag off; tests
covering the bipartite graph monkey-patch the setting before invoking
:func:`register_bipartite_observer`.
"""
from __future__ import annotations

import logging
import threading

from aqp.data.catalog.lineage import BaseLineageObserver, LineageEvent, get_lineage_bus
from aqp.lineage.graph.writer import LineageGraphWriter, get_default_graph_writer

logger = logging.getLogger(__name__)


_REGISTERED: BipartiteGraphObserver | None = None
_REGISTER_LOCK = threading.RLock()


class BipartiteGraphObserver(BaseLineageObserver):
    """Translate :class:`LineageEvent` into bipartite-graph rows.

    The observer is intentionally minimal: it delegates 100 % of the
    actual ORM work to :class:`LineageGraphWriter`. The only logic here
    is the should_handle gate so a misconfigured event (no source AND
    no target) silently skips rather than producing a useless transform
    vertex with zero edges.
    """

    name = "bipartite_graph"

    def __init__(self, writer: LineageGraphWriter | None = None) -> None:
        self._writer = writer or get_default_graph_writer()

    def should_handle(self, event: LineageEvent) -> bool:
        # We accept events with at least one endpoint. Events that
        # describe pure metadata operations (e.g. ``datahub_emit``
        # without a target) still produce a useful transform vertex
        # with no edges, so we keep them.
        return bool(getattr(event, "transform_kind", None))

    def handle(self, event: LineageEvent) -> None:
        self._writer.record_event(event)


def is_bipartite_graph_enabled() -> bool:
    """Read ``settings.lineage_graph_enabled`` defensively."""
    try:
        from aqp.config import settings

        return bool(getattr(settings, "lineage_graph_enabled", False))
    except Exception:  # noqa: BLE001
        return False


def register_bipartite_observer(*, force: bool = False) -> BipartiteGraphObserver | None:
    """Idempotently attach the observer to the singleton lineage bus.

    No-ops when ``lineage_graph_enabled`` is false unless ``force``
    is set (used by tests that need the observer regardless).
    Returns the registered observer (or ``None`` if registration was
    skipped).
    """
    if not (force or is_bipartite_graph_enabled()):
        return None
    global _REGISTERED
    with _REGISTER_LOCK:
        if _REGISTERED is not None:
            return _REGISTERED
        observer = BipartiteGraphObserver()
        get_lineage_bus().register(observer)
        _REGISTERED = observer
        logger.info("BipartiteGraphObserver registered on LineageBus")
        return _REGISTERED


def unregister_bipartite_observer() -> None:
    """Drop the bipartite observer (tests + rollback runbook)."""
    global _REGISTERED
    with _REGISTER_LOCK:
        if _REGISTERED is None:
            return
        try:
            get_lineage_bus().unregister(_REGISTERED)
        except Exception:  # noqa: BLE001
            pass
        _REGISTERED = None


__all__ = [
    "BipartiteGraphObserver",
    "is_bipartite_graph_enabled",
    "register_bipartite_observer",
    "unregister_bipartite_observer",
]
