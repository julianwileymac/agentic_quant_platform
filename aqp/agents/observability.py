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


@contextlib.contextmanager
def node_span(
    adapter_alias: str,
    node_name: str,
    *,
    workflow_run_id: str | None = None,
    workflow_spec_name: str | None = None,
    **attributes: Any,
) -> Iterator[dict[str, Any]]:
    """Per-node OTEL span used by :class:`aqp.agents.orchestration.runtime.WorkflowRuntime`.

    Thin wrapper over :func:`trace_step` that pre-fills the
    ``adapter`` / ``node`` / ``workflow.*`` attributes the Phase 2
    runtime needs. Every adapter transition opens one of these so the
    final ``WorkflowRunResult`` carries a complete latency /
    branch-decision trace without each adapter having to import OTEL
    directly.

    Yields the same span data dict :func:`trace_step` yields; callers
    can stash ``status`` / ``cost_usd`` / ``decision`` etc. and they
    end up on the OTEL span when configured.
    """
    span_attrs: dict[str, Any] = {
        "adapter": adapter_alias,
        "node": node_name,
    }
    if workflow_run_id:
        span_attrs["workflow.run_id"] = workflow_run_id
    if workflow_spec_name:
        span_attrs["workflow.spec_name"] = workflow_spec_name
    span_attrs.update(attributes)
    span_name = f"workflow.{adapter_alias}.{node_name}"
    with trace_step(span_name, **span_attrs) as data:
        yield data


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


# ---------------------------------------------------------------------------
# Assistant-engine span helpers (Phase 7)
# ---------------------------------------------------------------------------
#
# These wrap :func:`trace_step` with the AQP-flavoured projection of the
# OpenTelemetry GenAI semantic conventions where it makes sense:
#
# - ``gen_ai.agent.name`` — registered AssistantSpec / AgentSpec slug.
# - ``gen_ai.agent.id`` — the runtime ``run_id`` (UUID).
# - ``gen_ai.agent.version`` — hash-locked spec version id when known.
# - ``gen_ai.conversation.id`` — the assistant session id.
#
# Plus AQP-native attributes the legacy timeline already understands:
# ``assistant.run_id`` / ``workflow.run_id`` / ``tool.name`` /
# ``cost_usd`` / ``duration_ms`` / ``finish_reason`` / ``status``. We
# prefer the conventional OTEL keys when both are emitted, but the
# AQP-native keys remain so existing dashboards keep rendering without
# a backend change.


def _assistant_attributes(
    *,
    assistant_spec_name: str | None,
    run_id: str | None,
    session_id: str | None,
    spec_version_id: str | None,
    extra: dict[str, Any] | None,
) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    if assistant_spec_name:
        attrs["gen_ai.agent.name"] = assistant_spec_name
        attrs["assistant.spec_name"] = assistant_spec_name
    if run_id:
        attrs["gen_ai.agent.id"] = run_id
        attrs["assistant.run_id"] = run_id
    if session_id:
        attrs["gen_ai.conversation.id"] = session_id
        attrs["assistant.session_id"] = session_id
    if spec_version_id:
        attrs["gen_ai.agent.version"] = spec_version_id
        attrs["assistant.spec_version_id"] = spec_version_id
    if extra:
        attrs.update(extra)
    return attrs


@contextlib.contextmanager
def assistant_run_span(
    *,
    assistant_spec_name: str,
    run_id: str,
    session_id: str | None = None,
    spec_version_id: str | None = None,
    mode: str | None = None,
    target_ref: str | None = None,
    **extra: Any,
) -> Iterator[dict[str, Any]]:
    """Top-level span wrapping one ``AssistantRuntime.run`` call."""
    attrs = _assistant_attributes(
        assistant_spec_name=assistant_spec_name,
        run_id=run_id,
        session_id=session_id,
        spec_version_id=spec_version_id,
        extra={
            "assistant.mode": mode,
            "assistant.target_ref": target_ref,
            **extra,
        },
    )
    with trace_step("assistant.run", **attrs) as data:
        yield data


@contextlib.contextmanager
def assistant_message_span(
    *,
    run_id: str,
    role: str,
    turn: int,
    session_id: str | None = None,
    **extra: Any,
) -> Iterator[dict[str, Any]]:
    """Span around persisting / streaming a single assistant message."""
    attrs = _assistant_attributes(
        assistant_spec_name=None,
        run_id=run_id,
        session_id=session_id,
        spec_version_id=None,
        extra={
            "assistant.message.role": role,
            "assistant.message.turn": int(turn),
            **extra,
        },
    )
    with trace_step("assistant.message", **attrs) as data:
        yield data


@contextlib.contextmanager
def model_call_span(
    *,
    run_id: str | None = None,
    provider: str,
    model: str,
    tier: str | None = None,
    **extra: Any,
) -> Iterator[dict[str, Any]]:
    """Span around an LLM call dispatched through ``router_complete``.

    Mirrors the GenAI convention attribute names where they apply:
    ``gen_ai.system`` (= provider) and ``gen_ai.request.model``.
    """
    attrs = _assistant_attributes(
        assistant_spec_name=None,
        run_id=run_id,
        session_id=None,
        spec_version_id=None,
        extra={
            "gen_ai.system": provider,
            "gen_ai.request.model": model,
            "model.tier": tier,
            **extra,
        },
    )
    with trace_step("assistant.model_call", **attrs) as data:
        yield data


@contextlib.contextmanager
def tool_call_span(
    *,
    run_id: str | None = None,
    tool_name: str,
    arguments: Any | None = None,
    **extra: Any,
) -> Iterator[dict[str, Any]]:
    """Span around a tool invocation inside the assistant loop."""
    attrs = _assistant_attributes(
        assistant_spec_name=None,
        run_id=run_id,
        session_id=None,
        spec_version_id=None,
        extra={"tool.name": tool_name, **extra},
    )
    if arguments is not None:
        attrs["tool.arguments"] = str(arguments)[:512]
    with trace_step("assistant.tool_call", **attrs) as data:
        yield data


@contextlib.contextmanager
def memory_retrieval_span(
    *,
    run_id: str | None = None,
    memory_kind: str,
    role: str | None = None,
    top_k: int | None = None,
    **extra: Any,
) -> Iterator[dict[str, Any]]:
    """Span around an episodic / hybrid memory recall."""
    attrs = _assistant_attributes(
        assistant_spec_name=None,
        run_id=run_id,
        session_id=None,
        spec_version_id=None,
        extra={
            "memory.kind": memory_kind,
            "memory.role": role,
            "memory.top_k": top_k,
            **extra,
        },
    )
    with trace_step("assistant.memory_retrieval", **attrs) as data:
        yield data


@contextlib.contextmanager
def sandbox_validate_span(
    *,
    run_id: str | None = None,
    backend: str,
    command_count: int,
    **extra: Any,
) -> Iterator[dict[str, Any]]:
    """Span around :meth:`AssistantSandbox.validate_command_set`."""
    attrs = _assistant_attributes(
        assistant_spec_name=None,
        run_id=run_id,
        session_id=None,
        spec_version_id=None,
        extra={
            "sandbox.backend": backend,
            "sandbox.command_count": int(command_count),
            **extra,
        },
    )
    with trace_step("assistant.sandbox_validate", **attrs) as data:
        yield data


@contextlib.contextmanager
def workflow_handoff_span(
    *,
    run_id: str | None = None,
    target_kind: str,
    target_ref: str,
    **extra: Any,
) -> Iterator[dict[str, Any]]:
    """Span around the assistant->agent / assistant->workflow dispatch."""
    attrs = _assistant_attributes(
        assistant_spec_name=None,
        run_id=run_id,
        session_id=None,
        spec_version_id=None,
        extra={
            "assistant.target_kind": target_kind,
            "assistant.target_ref": target_ref,
            **extra,
        },
    )
    with trace_step("assistant.workflow_handoff", **attrs) as data:
        yield data


__all__ = [
    "assistant_message_span",
    "assistant_run_span",
    "cost_summary",
    "emit_progress",
    "memory_retrieval_span",
    "model_call_span",
    "node_span",
    "sandbox_validate_span",
    "tool_call_span",
    "trace_step",
    "workflow_handoff_span",
]
