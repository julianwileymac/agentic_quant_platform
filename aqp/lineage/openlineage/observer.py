"""Transactional-outbox observer for OpenLineage relay (Workstream B).

Mounted on the singleton :class:`LineageBus` alongside the existing
:class:`WriterLineageObserver` and the workstream-A
:class:`BipartiteGraphObserver`. Translates each :class:`LineageEvent`
into an OpenLineage ``RunEvent`` via
:func:`aqp_event_to_openlineage` and writes a row into
``lineage_openlineage_outbox``. A background Celery beat task drains
the outbox by POSTing to Marquez.

The observer is feature-flagged behind
``settings.lineage_openlineage_relay_enabled`` so deployments that
don't yet have Marquez stood up can leave it off without any code
change.
"""
from __future__ import annotations

import logging
import threading

from aqp.data.catalog.lineage import BaseLineageObserver, LineageEvent, get_lineage_bus
from aqp.lineage.openlineage.mapper import aqp_event_to_openlineage

logger = logging.getLogger(__name__)


_REGISTERED: OpenLineageOutboxObserver | None = None
_REGISTER_LOCK = threading.RLock()


class OpenLineageOutboxObserver(BaseLineageObserver):
    """Persist an :class:`OpenLineageOutbox` row per lineage event.

    The observer NEVER POSTs to Marquez directly — that's the Celery
    relay task's job. Coupling the observer to a network call would
    block whatever transaction emitted the lineage event; the outbox
    decouples emission from delivery.
    """

    name = "openlineage_outbox"

    def should_handle(self, event: LineageEvent) -> bool:
        return bool(getattr(event, "transform_kind", None))

    def handle(self, event: LineageEvent) -> None:
        try:
            self._write_outbox_row(event)
        except Exception:  # noqa: BLE001
            # Lineage is a side channel; never block the data write.
            logger.warning(
                "OpenLineageOutboxObserver.handle failed for kind=%s",
                getattr(event, "transform_kind", "?"),
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _write_outbox_row(self, event: LineageEvent) -> None:
        from aqp.config import settings
        from aqp.persistence.db import get_session
        from aqp.persistence.models_openlineage import OpenLineageOutbox

        ol_namespace = str(
            getattr(settings, "lineage_openlineage_namespace", "aqp") or "aqp"
        )
        payload = aqp_event_to_openlineage(event, ol_namespace=ol_namespace)
        job = payload.get("job") or {}
        run = payload.get("run") or {}

        with get_session() as session:
            row = OpenLineageOutbox(
                payload=payload,
                eventType=str(payload.get("eventType") or "COMPLETE"),
                job_namespace=str(job.get("namespace") or ol_namespace),
                job_name=str(job.get("name") or "unknown"),
                run_id=str(run.get("runId") or ""),
                attempts=0,
            )
            session.add(row)
            session.commit()


def is_openlineage_relay_enabled() -> bool:
    """Read the feature flag defensively."""
    try:
        from aqp.config import settings

        return bool(getattr(settings, "lineage_openlineage_relay_enabled", False))
    except Exception:  # noqa: BLE001
        return False


def register_openlineage_observer(*, force: bool = False) -> OpenLineageOutboxObserver | None:
    """Idempotently attach the observer to the singleton lineage bus.

    No-ops when the relay feature flag is off unless ``force`` is set
    (used by tests that need the observer regardless).
    """
    if not (force or is_openlineage_relay_enabled()):
        return None
    global _REGISTERED
    with _REGISTER_LOCK:
        if _REGISTERED is not None:
            return _REGISTERED
        observer = OpenLineageOutboxObserver()
        get_lineage_bus().register(observer)
        _REGISTERED = observer
        logger.info("OpenLineageOutboxObserver registered on LineageBus")
        return _REGISTERED


def unregister_openlineage_observer() -> None:
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
    "OpenLineageOutboxObserver",
    "is_openlineage_relay_enabled",
    "register_openlineage_observer",
    "unregister_openlineage_observer",
]
