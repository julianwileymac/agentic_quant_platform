"""OpenTelemetry observability for AQP.

This package is **soft-optional**: if ``opentelemetry-*`` isn't installed,
every helper becomes a no-op so application code can call them freely
without guards. Install the extra to enable real tracing::

    pip install -e ".[otel]"
"""
from __future__ import annotations

from aqp.observability.decorators import traced
from aqp.observability.tracing import (
    configure_tracing,
    get_tracer,
    instrument_celery,
    instrument_fastapi,
    shutdown_tracing,
)

__all__ = [
    "configure_tracing",
    "get_tracer",
    "instrument_celery",
    "instrument_fastapi",
    "shutdown_tracing",
    "traced",
]
