"""``snippet.python`` executor — user-authored Python in the Tier-1 sandbox.

Phase 1 ships an in-process executor that reuses the
:class:`aqp.lab.eda.kernel.EdaKernel` runtime so the snippet sandbox
posture (AST guard via :func:`_ast_safety_check`, captured stdout /
stderr / repr, isolated namespace) matches the EDA mode behaviour
the snippet was promoted from. Phase 4 will swap this for the
``gVisor-Docker Tier-2`` runner per AGENTS rule 39 + plan §4 — both
paths share the same input contract so the rest of the graph is
unaware of the sandbox kind.

Snippet resolution:

- ``params['snippet_id']`` — preferred path; loads the snippet source
  via :func:`aqp.lab.snippets.describe_snippet`.
- ``params['source']`` — inline fallback used by the EDA promote
  endpoint when a snippet has not been persisted yet.

Input wiring:

- The executor exposes any upstream FRAME locator under
  ``locals['_inputs'][port_name]`` so the snippet body can read
  ``df = _inputs['in']`` directly. The lookup is read-only and the
  payload is whatever the upstream wrote (an in-process Arrow handle,
  a path, or a placeholder dict).

Output wiring:

- The snippet's final-expression value is stored on the locator as
  ``{"kind": "snippet_inline", "value_repr": "...", "type": "..."}``
  for the run-history drawer to render. Heavier outputs (DataFrames,
  Arrow tables) get an in-process pointer the next node can read via
  the same shared-extras path the inline canvas already uses.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from aqp.lab.executors._types import NodeContext, NodeResult

logger = logging.getLogger(__name__)


def execute(node: Any, ctx: NodeContext) -> NodeResult:  # noqa: D401
    params = dict(getattr(node, "params", {}) or {})
    snippet_id = params.get("snippet_id")
    source = params.get("source")

    if not source and snippet_id:
        source = _load_snippet_source(str(snippet_id))
    if not source:
        return NodeResult(
            status="error",
            error="snippet.python requires either params.snippet_id or params.source",
            log_label="snippet.python:missing_source",
        )

    # Sandbox tier selection. Phase 1 always uses tier1 (in-process
    # EdaKernel); Phase 4 promotes to tier2 (gVisor) when configured.
    tier = str(params.get("tier") or "tier1").lower()
    if tier not in {"tier1", "tier2"}:
        return NodeResult(
            status="error",
            error=f"unknown snippet tier {tier!r}; valid: tier1, tier2",
            log_label="snippet.python:bad_tier",
        )

    started = time.perf_counter()
    try:
        if tier == "tier1":
            result = _run_tier1(
                source=str(source),
                ctx=ctx,
                preload=dict(params.get("preload") or {}),
            )
        else:
            result = _run_tier2(source=str(source), ctx=ctx, params=params)
    except Exception as exc:  # noqa: BLE001
        logger.exception("snippet.python run failed node_id=%s", ctx.node_id)
        return NodeResult(
            status="error",
            error=f"snippet exec crashed: {exc}",
            log_label="snippet.python:exec_crash",
        )

    duration_ms = (time.perf_counter() - started) * 1000.0
    metrics: dict[str, Any] = {
        "duration_ms": float(round(duration_ms, 3)),
        "tier": tier,
        "stdout_chars": len(result.get("stdout") or ""),
        "stderr_chars": len(result.get("stderr") or ""),
    }
    if result.get("status") == "error":
        return NodeResult(
            status="error",
            error=str(result.get("error") or "snippet returned error"),
            metrics=metrics,
            log_label=f"snippet.python:{tier}:error",
        )

    locator = {
        "kind": "snippet_inline",
        "tier": tier,
        "snippet_id": snippet_id,
        "value_repr": result.get("repr") or "",
        "stdout": result.get("stdout") or "",
        "stderr": result.get("stderr") or "",
    }
    # If the snippet stored its primary output in extras (e.g. a
    # DataFrame), surface a stable handle so downstream FRAME nodes
    # can pick it up via the inline-canvas extras passthrough.
    primary = result.get("primary_output")
    if primary is not None:
        ctx.extras.setdefault("snippet_outputs", {})[ctx.node_id] = primary
        locator["primary_in_extras"] = True
    return NodeResult(
        status="done",
        output_locator=locator,
        metrics=metrics,
        log_label=f"snippet.python:{tier}:done",
    )


# ---------------------------------------------------------------------------
# Tier 1 — in-process EdaKernel (Phase 1)
# ---------------------------------------------------------------------------


def _run_tier1(*, source: str, ctx: NodeContext, preload: dict[str, Any]) -> dict[str, Any]:
    """Run the snippet through an ephemeral :class:`EdaKernel`.

    Each call gets its own kernel so the snippet namespace is isolated
    from any long-lived EDA session. Inputs are injected into the
    kernel namespace as ``_inputs`` + flattened keys so common forms
    (``in``, ``left``, ``right``) work without an extra dict lookup.
    """
    from aqp.lab.eda.kernel import EdaKernel

    kernel = EdaKernel(session_id=f"snippet-{ctx.node_id}")
    # Inject upstream locators + preload (user-supplied helpers).
    inputs = dict(ctx.upstream or {})
    kernel._namespace["_inputs"] = inputs  # noqa: SLF001 — explicit Phase-1 injection
    for name, value in inputs.items():
        # Skip names that collide with builtins / preloaded helpers.
        if name in {"pd", "np", "db", "scan", "iceberg", "duckdb"}:
            continue
        kernel._namespace[name] = value  # noqa: SLF001
    for name, value in (preload or {}).items():
        kernel._namespace[name] = value  # noqa: SLF001

    cell_id = f"snip-{ctx.node_id}"
    outcome = kernel.execute_cell(cell_id, source)
    primary_output = None
    if outcome.status == "done":
        # Prefer ``out`` then ``df`` then the last-bound name.
        for candidate in ("out", "df", "frame"):
            value = kernel.get_var(candidate)
            if value is not None:
                primary_output = value
                break
    return {
        "status": outcome.status,
        "stdout": outcome.stdout,
        "stderr": outcome.stderr,
        "repr": outcome.repr_value,
        "error": outcome.error,
        "primary_output": primary_output,
    }


# ---------------------------------------------------------------------------
# Tier 2 — gVisor-Docker (Phase 4 placeholder)
# ---------------------------------------------------------------------------


def _run_tier2(*, source: str, ctx: NodeContext, params: dict[str, Any]) -> dict[str, Any]:
    """Phase-4 placeholder for the gVisor / Docker server-side sandbox.

    Returns a structured ``not_yet_implemented`` payload so the runtime
    surfaces a clear actionable error in the run-history drawer rather
    than silently degrading to Tier 1. The Phase 4 snippet runner
    swaps this for a real subprocess + ``runsc`` invocation per plan
    §4.
    """
    from aqp.config import settings

    runtime = getattr(settings, "aqp_lab_sandbox_runtime", "none") or "none"
    return {
        "status": "error",
        "stdout": "",
        "stderr": "",
        "repr": None,
        "error": (
            f"snippet.python tier2 sandbox not yet ready (settings.aqp_lab_sandbox_runtime="
            f"{runtime!r}); rerun with params.tier='tier1' or wait for Phase 4."
        ),
        "primary_output": None,
    }


# ---------------------------------------------------------------------------
# Snippet source resolution
# ---------------------------------------------------------------------------


def _load_snippet_source(snippet_id: str) -> str | None:
    try:
        from aqp.lab.snippets import describe_snippet
    except Exception:  # noqa: BLE001
        return None
    descriptor = describe_snippet(snippet_id)
    if descriptor is None:
        return None
    if not descriptor.ast_safe:
        logger.warning(
            "snippet %r is flagged ast_safe=False; refusing to execute",
            snippet_id,
        )
        return None
    return descriptor.source


__all__ = ["execute"]
