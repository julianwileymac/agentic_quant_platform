"""OpenTelemetry instrumentation."""

from .setup import setup_telemetry
from .tracing import traced, get_tracer

__all__ = ["setup_telemetry", "traced", "get_tracer"]
