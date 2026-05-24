"""Structured logging for QuantBot bots.

Uses :mod:`structlog` (when available) to emit JSON lines with
correlation-id fields injected automatically:

- ``bot_id`` / ``strategy_id`` / ``run_id`` — bot identity
- ``trace_id`` / ``span_id`` — OTel correlation (pulled from
  ``opentelemetry.trace.get_current_span``)
- ``correlation_id`` — domain id (FIX ``ClOrdID`` or on-chain
  ``txHash``) propagated through the order pipeline.

Falls back to stdlib :class:`logging.LoggerAdapter` when structlog
isn't installed.
"""
from __future__ import annotations

import logging
import os
from typing import Any


def configure_structlog(*, json_output: bool = True) -> None:
    """Initialise structlog. Idempotent.

    JSON output is the default for production (compatible with Loki /
    Elasticsearch); pass ``json_output=False`` for human-readable
    console output in dev.
    """
    try:
        import structlog  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        return

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        _add_otel_trace_ids,
    ]
    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, os.environ.get("AQP_BOTS_LOG_LEVEL", "INFO").upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


def _add_otel_trace_ids(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    try:
        from opentelemetry import trace  # type: ignore[import-not-found]

        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx.is_valid:
            event_dict.setdefault("trace_id", format(ctx.trace_id, "032x"))
            event_dict.setdefault("span_id", format(ctx.span_id, "016x"))
    except Exception:  # noqa: BLE001
        pass
    return event_dict


def get_logger(name: str = "quantbot", **bindings: Any) -> Any:
    """Return a structured logger bound with the given context."""
    try:
        import structlog  # type: ignore[import-not-found]

        return structlog.get_logger(name).bind(**bindings)
    except Exception:  # noqa: BLE001
        log = logging.getLogger(name)
        return logging.LoggerAdapter(log, extra=bindings)


__all__ = ["configure_structlog", "get_logger"]
