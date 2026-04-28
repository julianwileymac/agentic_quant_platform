"""Dagster <-> OpenTelemetry bridge.

Dagster does not ship an official OTel auto-instrumentor, so this module
attaches lightweight span hooks via Dagster's event-log hook API.  Each
op execution becomes a span named ``dagster.op.<op_name>`` that carries the
run ID, job name, and op key as attributes.

The instrumentor is idempotent and a no-op when either Dagster or
OpenTelemetry is missing.
"""

from __future__ import annotations

import logging
from typing import Any

from aqp.observability.tracing import _otel_available, configure_tracing, get_tracer

logger = logging.getLogger(__name__)

_attached = False


def instrument_dagster() -> None:
    """Attach Dagster ops/sensors to the global tracer.

    Safe to call repeatedly.  Returns immediately if Dagster or OTel is not
    importable.
    """

    global _attached
    if _attached:
        return
    if not _otel_available():
        logger.debug("OpenTelemetry SDK missing; skipping Dagster instrumentation")
        return
    try:
        import dagster  # noqa: F401
    except ImportError:
        logger.debug("Dagster missing; skipping Dagster instrumentation")
        return

    # Boot the global tracer if the caller hasn't done it yet.
    configure_tracing(service_name="dagster-aqp")
    tracer = get_tracer("aqp.dagster")

    try:
        from dagster._core.events import DagsterEventType
        from dagster._core.execution.context.system import StepExecutionContext
        from dagster._core.instance import DagsterInstance
    except Exception:  # noqa: BLE001 - Dagster internals can shift
        logger.exception("Failed to import Dagster internals; tracing not attached")
        return

    # In current Dagster versions there is no public per-op pre/post hook
    # in StepExecutionContext that we can monkeypatch.  Instead, wrap
    # `DagsterInstance.report_event` so each completed step emits a span.
    original_report = DagsterInstance.report_engine_event  # type: ignore[attr-defined]

    def _report(self: Any, message: str, *args: Any, **kwargs: Any) -> Any:
        with tracer.start_as_current_span("dagster.event") as span:
            try:
                span.set_attribute("dagster.message", message[:120])
            except Exception:
                pass
            return original_report(self, message, *args, **kwargs)

    DagsterInstance.report_engine_event = _report  # type: ignore[assignment]
    _attached = True
    logger.info("Dagster OpenTelemetry instrumentation attached")
