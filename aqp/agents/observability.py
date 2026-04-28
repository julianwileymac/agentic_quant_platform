"""Agent observability: OTEL spans + cost roll-ups + progress emit hooks.

Lightweight wrappers so the rest of the agent code is free of telemetry
boilerplate. Instances of :class:`AgentTelemetry` are created per-run by
:class:`aqp.agents.runtime.AgentRuntime` (when telemetry is enabled).
"""
from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import Iterator
from typing import Any

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def trace_step(name: str, **attributes: Any) -> Iterator[dict[str, Any]]:
    """Yield a small span context that records duration + outcome.

    When OpenTelemetry is configured (via
    :mod:`aqp.observability`) this also opens a real OTEL span; otherwise
    falls back to a plain dict so callers don't need to handle the
    optional dep.
    """
    span_data: dict[str, Any] = {"name": name, "attrs": dict(attributes)}
    span = None
    try:
        from aqp.observability import get_tracer

        span = get_tracer("aqp.agents").start_span(name)
        for k, v in attributes.items():
            try:
                span.set_attribute(k, v)
            except Exception:  # pragma: no cover
                pass
    except Exception:  # pragma: no cover
        span = None
    start = time.perf_counter()
    try:
        yield span_data
        if span is not None:
            span.set_attribute("status", "ok")
    except Exception as exc:
        span_data["error"] = str(exc)
        if span is not None:
            try:
                span.set_attribute("status", "error")
                span.set_attribute("error.message", str(exc))
            except Exception:  # pragma: no cover
                pass
        raise
    finally:
        span_data["duration_ms"] = (time.perf_counter() - start) * 1000.0
        if span is not None:
            try:
                span.end()
            except Exception:  # pragma: no cover
                pass


def emit_progress(task_id: str | None, stage: str, message: str, **extras: Any) -> None:
    """Forward to the shared task progress bus."""
    if not task_id:
        return
    try:
        from aqp.tasks._progress import emit

        emit(task_id, stage, message, **extras)
    except Exception:  # pragma: no cover
        logger.debug("progress emit failed", exc_info=True)


def cost_summary(steps: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate cost / call counts per step.kind."""
    by_kind: dict[str, dict[str, float]] = {}
    total_cost = 0.0
    for step in steps:
        kind = step.get("kind") or "unknown"
        bucket = by_kind.setdefault(kind, {"cost_usd": 0.0, "n": 0})
        bucket["cost_usd"] += float(step.get("cost_usd") or 0.0)
        bucket["n"] += 1
        total_cost += float(step.get("cost_usd") or 0.0)
    return {"by_kind": by_kind, "total_cost_usd": round(total_cost, 6)}


__all__ = ["cost_summary", "emit_progress", "trace_step"]
