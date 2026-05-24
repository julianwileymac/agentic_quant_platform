"""QuantBot Platform telemetry — OpenTelemetry + Prometheus + structlog.

Six modules:

- :mod:`aqp_bots.telemetry.otel` — bridges
  :func:`aqp.observability.tracing.configure_tracing` (which delegates
  to ``rpi_k8s_sdk.tracing``) with bot-scoped resource attributes.
- :mod:`aqp_bots.telemetry.hft_processor` — :class:`HFTSpanProcessor`
  using a lock-free SPSC ring buffer + shared-memory exporter for
  microsecond-grade HFT span recording.
- :mod:`aqp_bots.telemetry.metrics` — Prometheus client wrapper with
  explicit microsecond histogram buckets.
- :mod:`aqp_bots.telemetry.logging` — structlog JSON output with
  correlation-id fields.
- :mod:`aqp_bots.telemetry.health` — /healthz, /readyz, /metrics
  endpoint helpers.
"""
from __future__ import annotations

from aqp_bots.telemetry.health import build_health_app
from aqp_bots.telemetry.hft_processor import HFTSpanProcessor
from aqp_bots.telemetry.logging import configure_structlog, get_logger
from aqp_bots.telemetry.metrics import (
    HFT_LATENCY_BUCKETS,
    QuantBotMetrics,
    get_metrics,
)
from aqp_bots.telemetry.otel import configure_bot_tracing, get_bot_tracer

__all__ = [
    "HFT_LATENCY_BUCKETS",
    "HFTSpanProcessor",
    "QuantBotMetrics",
    "build_health_app",
    "configure_bot_tracing",
    "configure_structlog",
    "get_bot_tracer",
    "get_logger",
    "get_metrics",
]
