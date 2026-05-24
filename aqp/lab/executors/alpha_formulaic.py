"""``alpha.formulaic`` — wraps :func:`aqp.data.expressions_dsl.compile_to_factor_node`.

WorldQuant BRAIN-style expression DSL. The AST sandbox in
:mod:`aqp.data.expressions_dsl` ensures NO ``exec`` / ``eval`` of raw
user input ever happens (AGENTS rule 39); we just wrap the compile +
``compute`` call as a Lab node.

Params:

- ``formula`` (str, required) — DSL expression, e.g.
  ``Ts_Corr(close, volume, 20) * Decay_Linear(returns, 10)``.
- ``alias`` (str, default ``"alpha"``) — output column name.
- ``signal_clip`` (float | None) — optional symmetric clip for the
  resulting signal.
"""
from __future__ import annotations

import numpy as np

from aqp.lab.executors._helpers import (
    base_locator,
    resolve_upstream_frame,
    stash_arrow_output,
)
from aqp.lab.executors._types import NodeContext, NodeResult


def execute(node, ctx: NodeContext) -> NodeResult:
    params = dict(getattr(node, "params", {}) or {})
    formula = str(params.get("formula") or "").strip()
    alias = str(params.get("alias") or "alpha")
    clip_value = params.get("signal_clip")
    if not formula:
        return NodeResult(status="error", error="alpha.formulaic requires non-empty 'formula'")

    df = resolve_upstream_frame(ctx)
    if df is None:
        return NodeResult(status="error", error="alpha.formulaic needs an upstream OHLCV frame")

    try:
        from aqp.data.expressions_dsl import (
            SymbolicAlphaError,
            compile_to_factor_node,
        )
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=f"expressions_dsl import failed: {exc}",
        )

    try:
        factor = compile_to_factor_node(formula, name=alias)
    except SymbolicAlphaError as exc:
        # Per AGENTS rule 39 + symbolic-alphas rule, compile failure is
        # surfaced as a structured error with the BRAIN-compat message.
        return NodeResult(
            status="error",
            error=f"alpha.formulaic compile rejected: {exc}",
            log_label="symbolic_alpha_compile_error",
        )

    try:
        signal = factor.compute(df)
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=f"alpha.formulaic compute failed: {exc}",
        )

    out = df.copy()
    if clip_value is not None:
        try:
            v = float(clip_value)
            signal = signal.clip(lower=-v, upper=v) if hasattr(signal, "clip") else np.clip(signal, -v, v)
        except Exception:  # noqa: BLE001
            pass
    out[alias] = signal
    stash_arrow_output(ctx, node.id, out)
    return NodeResult(
        status="done",
        output_locator={
            **base_locator(node.id, out),
            "formula_hash": factor.formula_hash if hasattr(factor, "formula_hash") else None,
            "alias": alias,
        },
        metrics={
            "alias": alias,
            "n_obs": int(getattr(signal, "notna", lambda: signal)().sum()) if hasattr(signal, "notna") else 0,
        },
        log_label=f"formulaic:{alias}",
    )
