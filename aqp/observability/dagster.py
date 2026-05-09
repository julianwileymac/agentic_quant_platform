"""Dagster <-> OpenTelemetry bridge.

Dagster does not ship a stable public OTel integration hook. This module keeps
runtime setup safe by configuring tracing without monkeypatching Dagster
internals. Callers can optionally wrap blocks with :func:`dagster_span` when
they want explicit span boundaries.
"""

from __future__ import annotations

from contextlib import contextmanager
import logging
from typing import Iterator

from aqp.observability.tracing import _otel_available, configure_tracing, get_tracer

logger = logging.getLogger(__name__)

_attached = False


def instrument_dagster() -> None:
    """Initialise Dagster tracing setup without private-API patching."""

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
    _attached = True
    logger.info("Dagster OpenTelemetry instrumentation initialized")


@contextmanager
def dagster_span(name: str, **attributes: str | int | float | bool) -> Iterator[None]:
    """Create an explicit Dagster-adjacent span when tracing is enabled."""
    if not _attached or not _otel_available():
        yield
        return
    tracer = get_tracer("aqp.dagster")
    with tracer.start_as_current_span(name) as span:
        for key, value in attributes.items():
            try:
                span.set_attribute(key, value)
            except Exception:  # noqa: BLE001
                continue
        yield


__all__ = ["dagster_span", "instrument_dagster"]
