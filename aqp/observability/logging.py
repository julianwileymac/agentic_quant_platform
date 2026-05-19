"""Structured JSON logging for AQP — Phase 4a control-plane maturation.

Configures :mod:`structlog` to emit one-line JSON records with the
following fields auto-injected on every log statement:

- ``timestamp`` — ISO-8601 with timezone.
- ``level`` — log level (``info``, ``warning``, ``error``, …).
- ``logger`` — Python logger name (module path).
- ``event`` — the message string (free-form).
- ``trace_id`` / ``span_id`` — pulled from the active OpenTelemetry
  span when one is recording. Empty strings otherwise.
- ``request_id`` — bound on every HTTP request by
  :class:`aqp.api.middleware.CorrelationIDMiddleware`.
- Any extra ``key=value`` pairs the caller passed to the structlog
  logger (e.g. ``log.info("user_action", user_id=ctx.user_id)``).

The configuration is **safe to call multiple times** — both the API
process and every Celery worker subprocess invoke
:func:`configure_structured_logging` at startup. Routing structlog
through the stdlib ``logging`` chain means existing
``logging.getLogger(__name__).info(...)`` calls in the codebase get
the same JSON envelope without anyone having to migrate them.

When ``structlog`` is not installed (older / minimal images) the
configuration falls back to standard ``logging.basicConfig`` with a
JSON-ish format string so downstream log aggregators don't choke on
multi-line stack traces.
"""
from __future__ import annotations

import logging
import sys
from typing import Any


def _add_otel_context(logger: Any, method_name: str, event_dict: dict) -> dict:
    """structlog processor: inject active trace/span IDs into every record.

    Pulls from the OpenTelemetry context (set by FastAPI / Celery
    instrumentation). When no span is active or OTel isn't installed,
    leaves the keys empty so the JSON envelope stays uniform.
    """
    try:
        from opentelemetry import trace  # type: ignore[import-not-found]

        span = trace.get_current_span()
        ctx = span.get_span_context() if span is not None else None
        if ctx is not None and ctx.is_valid:
            event_dict["trace_id"] = format(ctx.trace_id, "032x")
            event_dict["span_id"] = format(ctx.span_id, "016x")
    except Exception:  # noqa: BLE001
        pass
    return event_dict


def _add_request_context(logger: Any, method_name: str, event_dict: dict) -> dict:
    """structlog processor: inject the active :class:`RequestContext`.

    Stamps ``user_id`` / ``workspace_id`` / ``org_id`` / ``project_id``
    onto every log line so log aggregators can filter by tenancy
    without the caller having to remember to attach kwargs.

    Best-effort — never raises. When no context is bound (CLI, tests),
    the keys are simply absent.
    """
    try:
        from aqp.auth.contextvars import current_request_context

        ctx = current_request_context.get()
        if ctx is not None:
            if ctx.user_id:
                event_dict.setdefault("user_id", ctx.user_id)
            if ctx.org_id:
                event_dict.setdefault("org_id", ctx.org_id)
            if ctx.workspace_id:
                event_dict.setdefault("workspace_id", ctx.workspace_id)
            if ctx.project_id:
                event_dict.setdefault("project_id", ctx.project_id)
    except Exception:  # noqa: BLE001
        pass
    return event_dict


def configure_structured_logging(level: str = "INFO") -> None:
    """Configure structlog + stdlib logging to emit one-line JSON records.

    Idempotent — safe to call once per process from FastAPI ``lifespan``
    and once per Celery worker via ``worker_process_init``.

    Falls back to plain ``logging.basicConfig`` when ``structlog`` is
    not installed so the AQP codebase keeps working on minimal images.
    """
    log_level = logging.getLevelName(level.upper()) if isinstance(level, str) else level

    try:
        import structlog
        from structlog.contextvars import merge_contextvars
        from structlog.stdlib import (
            BoundLogger,
            LoggerFactory,
            add_log_level,
            add_logger_name,
        )
    except ImportError:
        # No structlog -> fall back to a JSON-ish format string.
        logging.basicConfig(
            level=log_level,
            format='{"timestamp":"%(asctime)s","level":"%(levelname)s",'
            '"logger":"%(name)s","event":"%(message)s"}',
            stream=sys.stdout,
            force=True,
        )
        return

    # Configure structlog itself
    structlog.configure(
        processors=[
            merge_contextvars,
            add_log_level,
            add_logger_name,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _add_otel_context,
            _add_request_context,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=BoundLogger,
        context_class=dict,
        logger_factory=LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Route stdlib ``logging.getLogger(...)`` through structlog so the
    # codebase's existing 5,000+ ``logger.info(...)`` calls inherit the
    # JSON envelope automatically.
    handler = logging.StreamHandler(sys.stdout)
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=[
            add_log_level,
            add_logger_name,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _add_otel_context,
            _add_request_context,
        ],
        processor=structlog.processors.JSONRenderer(),
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    # Replace any pre-existing handlers so re-configuration cleans up
    # the previous run's stream rather than stacking handlers.
    root.handlers = [handler]
    root.setLevel(log_level)


def get_logger(name: str | None = None):
    """Return a structlog logger if available, else stdlib ``logging``.

    New code should prefer this helper over ``logging.getLogger`` so
    structured-fields-as-kwargs (``log.info("x", user_id=...)`` ) work
    natively. Existing ``logging.getLogger(__name__)`` callsites keep
    working — :func:`configure_structured_logging` rewires the root
    logger so they still produce JSON output.
    """
    try:
        import structlog

        return structlog.get_logger(name)
    except ImportError:
        return logging.getLogger(name)


__all__ = [
    "configure_structured_logging",
    "get_logger",
]
