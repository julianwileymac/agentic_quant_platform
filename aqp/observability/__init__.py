"""OpenTelemetry observability for AQP.

This package is **soft-optional**: if ``opentelemetry-*`` isn't installed,
every helper becomes a no-op so application code can call them freely
without guards. Install the extra to enable real tracing::

    pip install -e ".[otel]"

Where possible the helpers delegate to the canonical
``rpi_k8s_sdk.tracing.configure_tracing`` so the rpi_kubernetes platform
and AQP report into the same Jaeger / collector.  The legacy
``AQP_OTEL_*`` env names are still honored.
"""
from __future__ import annotations

from aqp.observability.dagster import instrument_dagster
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
    "instrument_dagster",
    "instrument_fastapi",
    "shutdown_tracing",
    "traced",
]
