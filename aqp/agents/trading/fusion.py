"""Deterministic signal fusion for the orchestration control plane.

A pure-Python module — zero LLM calls, zero RNG without an explicit
seed, zero side effects — that combines:

- **Quant signals** (numerical alpha / momentum scores).
- **Debate verdict** (Bull/Bear/PortfolioManager output from the
  Phase 2 :class:`aqp.agents.orchestration.adapters.debate_adapter.DialecticalDebateAdapter`).
- **Model predictions** (ML predictor scores keyed by ``vt_symbol``).
- **Risk overlay** (optional gross-exposure / per-symbol caps applied
  before the Phase 4 :class:`WeightCentricExecutionAdapter` runs).

The output is a :class:`FusionOutput` carrying the per-symbol target
weights plus a fully-typed audit envelope (rationale + per-contributor
attribution + confidence). The same inputs always produce the same
output — exercised by ``tests/agents/orchestration/test_fusion.py``.

Why deterministic-only here
---------------------------

Hard rule 39: LLM-emitted alpha formulas go through the AST sandbox
in :mod:`aqp.data.expressions_dsl`. Fusion happens AFTER that
sandbox; by the time we get here the upstream debate verdict and the
model predictions are already structured payloads. Letting an LLM
re-shape them at fusion time would break the deterministic-replay
contract the Phase 5 ``workflow_runs.replay`` endpoint depends on.

If a future workflow needs LLM-driven re-weighting, model it as a new
upstream node that produces a structured slot the deterministic
fusion can read — never inside this synth.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class FusionInputs:
    """Structured inputs to :func:`synthesize`.

    Every field is optional so a workflow that only produces, say,
    debate verdicts can still drive fusion (the deterministic combine
    simply weights the missing contributors at zero).

    Attributes
    ----------
    quant_signals:
        ``{vt_symbol: signed_strength_in_[-1, +1]}``. Positive values
        favour a long position; negative values favour short.
    debate_verdict:
        Output of the dialectical debate adapter. Reads
        ``action`` (``buy``/``sell``/``hold``), ``confidence``
        (``[0, 1]``), and the optional ``vt_symbol`` it applies to.
    model_predictions:
        ``{vt_symbol: predicted_score}``. Treated like
        ``quant_signals`` but with the model's own confidence on the
        sibling ``model_confidence`` field.
    model_confidence:
        Optional scalar in ``[0, 1]`` indicating the model's overall
        confidence (e.g. its validation Sharpe / r-squared). Used to
        down-weight the model_predictions contributor when low.
    risk_overlay:
        Optional dict carrying ``max_position_pct`` /
        ``max_gross_exposure`` overrides. Whatever isn't set falls
        back to :class:`aqp.risk.limits.RiskLimits` defaults inside
        the Phase 4 :class:`WeightCentricExecutionAdapter`.
    weights_prior:
        ``{contributor_name: weight in [0, 1]}`` — soft prior on the
        relative importance of each contributor. Defaults to an even
        split across whichever contributors are present.
    """

    quant_signals: dict[str, float] = field(default_factory=dict)
    debate_verdict: dict[str, Any] = field(default_factory=dict)
    model_predictions: dict[str, float] = field(default_factory=dict)
    model_confidence: float | None = None
    risk_overlay: dict[str, float] = field(default_factory=dict)
    weights_prior: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "quant_signals": dict(self.quant_signals),
            "debate_verdict": dict(self.debate_verdict),
            "model_predictions": dict(self.model_predictions),
            "model_confidence": self.model_confidence,
            "risk_overlay": dict(self.risk_overlay),
            "weights_prior": dict(self.weights_prior),
        }


@dataclass(slots=True)
class FusionOutput:
    """Deterministic output of :func:`synthesize`.

    The ``target_weights`` are a probability-like vector keyed by
    ``vt_symbol`` and ready to feed into the Phase 4
    :class:`WeightCentricExecutionAdapter` (which threads it through
    :class:`aqp.rl.portfolio.pipeline.WeightCentricPipeline` so the
    final orders ride the existing risk overlay).

    ``contributors`` carries the unscaled per-contributor weight maps
    so the studio + audit log can show "which input pushed which way".
    """

    target_weights: dict[str, float]
    rationale: str
    confidence: float
    contributors: dict[str, dict[str, float]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_weights": dict(self.target_weights),
            "rationale": self.rationale,
            "confidence": float(self.confidence),
            "contributors": {k: dict(v) for k, v in self.contributors.items()},
        }


# ---------------------------------------------------------------------------
# Public synth
# ---------------------------------------------------------------------------


def synthesize(inputs: FusionInputs) -> FusionOutput:
    """Combine the four contributors into a deterministic weight vector.

    Determinism: same inputs always produce the same output. No RNG,
    no time-dependent values, no external calls.

    Algorithm:

    1. Each contributor produces an unscaled per-symbol weight map.
    2. Contributors with no signal are dropped (weight 0).
    3. The remaining contributors are normalised by their prior
       weights so the combined output is a convex combination.
    4. The combined per-symbol vector is L1-normalised so abs(weights)
       sums to <= 1 (gross exposure cap before the risk overlay).
    5. Confidence is the prior-weighted average of each
       contributor's reported confidence.

    Risk overlay (``inputs.risk_overlay``) caps abs(weight) per
    symbol if ``max_position_pct`` is provided and clamps gross
    exposure if ``max_gross_exposure`` is provided. These caps are
    deliberately additive on top of whatever the
    :class:`WeightCentricExecutionAdapter` applies via the existing
    :class:`RiskLimits`.
    """
    quant_map = _normalise_signal_map(inputs.quant_signals)
    model_map = _normalise_signal_map(inputs.model_predictions)
    debate_map = _debate_map(inputs.debate_verdict)

    contributors: dict[str, dict[str, float]] = {}
    confidences: dict[str, float] = {}
    if quant_map:
        contributors["quant"] = quant_map
        confidences["quant"] = _average_abs(quant_map)
    if model_map:
        contributors["model"] = model_map
        weight_conf = (
            float(inputs.model_confidence)
            if inputs.model_confidence is not None
            else _average_abs(model_map)
        )
        confidences["model"] = max(0.0, min(1.0, weight_conf))
    if debate_map:
        contributors["debate"] = debate_map
        confidences["debate"] = (
            float(inputs.debate_verdict.get("confidence", 0.5))
            if isinstance(inputs.debate_verdict, Mapping)
            else 0.5
        )

    if not contributors:
        return FusionOutput(
            target_weights={},
            rationale="no contributors had a signal",
            confidence=0.0,
            contributors={},
        )

    priors = _resolve_priors(contributors, inputs.weights_prior)
    combined: dict[str, float] = {}
    for cname, weights in contributors.items():
        scale = priors.get(cname, 0.0)
        if scale <= 0:
            continue
        for sym, w in weights.items():
            combined[sym] = combined.get(sym, 0.0) + scale * float(w)

    combined = _l1_renormalise(combined)
    combined = _apply_overlay_caps(combined, inputs.risk_overlay)

    confidence = sum(
        priors.get(cname, 0.0) * confidences.get(cname, 0.0)
        for cname in contributors
    )
    confidence = max(0.0, min(1.0, confidence))

    rationale = _rationale_str(contributors, priors, combined, confidence)

    return FusionOutput(
        target_weights=combined,
        rationale=rationale,
        confidence=confidence,
        contributors=contributors,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _normalise_signal_map(signal: Mapping[str, Any]) -> dict[str, float]:
    """Coerce + clip signals to ``[-1, +1]``; drop NaN / inf / non-numeric."""
    out: dict[str, float] = {}
    for sym, value in (signal or {}).items():
        try:
            v = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(v):
            continue
        out[str(sym)] = max(-1.0, min(1.0, v))
    return out


def _debate_map(verdict: Mapping[str, Any]) -> dict[str, float]:
    """Translate a debate verdict into a per-symbol weight map.

    The deterministic Bull/Bear synth at
    :func:`aqp.agents.graph.dialectical._portfolio_manager_node`
    produces verdicts shaped ``{action, confidence, vt_symbol?, ...}``.
    When ``vt_symbol`` is missing the verdict is treated as a
    universe-wide bias and applied to every symbol at fusion time
    through the prior, not here.
    """
    if not isinstance(verdict, Mapping):
        return {}
    action = str(verdict.get("action") or "").lower()
    if action not in {"buy", "sell"}:
        return {}
    vt_symbol = verdict.get("vt_symbol")
    if not vt_symbol:
        return {}
    confidence = float(verdict.get("confidence", 0.5) or 0.5)
    confidence = max(0.0, min(1.0, confidence))
    sign = 1.0 if action == "buy" else -1.0
    return {str(vt_symbol): sign * confidence}


def _resolve_priors(
    contributors: Mapping[str, Any],
    weights_prior: Mapping[str, float],
) -> dict[str, float]:
    """Resolve per-contributor priors with a sane default + renormalise."""
    if weights_prior:
        out = {k: max(0.0, float(weights_prior.get(k, 0.0))) for k in contributors}
    else:
        out = {k: 1.0 for k in contributors}
    total = sum(out.values())
    if total <= 0:
        n = len(contributors)
        return {k: 1.0 / n for k in contributors}
    return {k: v / total for k, v in out.items()}


def _l1_renormalise(weights: Mapping[str, float]) -> dict[str, float]:
    total = sum(abs(v) for v in weights.values())
    if total <= 0:
        return {k: 0.0 for k in weights}
    return {k: v / total for k, v in weights.items()}


def _apply_overlay_caps(
    weights: Mapping[str, float],
    overlay: Mapping[str, Any],
) -> dict[str, float]:
    """Apply ``max_position_pct`` + ``max_gross_exposure`` caps in place."""
    out = dict(weights)
    max_position = overlay.get("max_position_pct") if isinstance(overlay, Mapping) else None
    if max_position is not None:
        cap = float(max_position)
        for sym in list(out):
            v = out[sym]
            if abs(v) > cap:
                out[sym] = math.copysign(cap, v)
    max_gross = overlay.get("max_gross_exposure") if isinstance(overlay, Mapping) else None
    if max_gross is not None:
        cap = float(max_gross)
        gross = sum(abs(v) for v in out.values())
        if gross > cap and gross > 0:
            scale = cap / gross
            out = {sym: v * scale for sym, v in out.items()}
    return out


def _average_abs(weights: Mapping[str, float]) -> float:
    if not weights:
        return 0.0
    return sum(abs(v) for v in weights.values()) / len(weights)


def _rationale_str(
    contributors: Mapping[str, Mapping[str, float]],
    priors: Mapping[str, float],
    combined: Mapping[str, float],
    confidence: float,
) -> str:
    parts = [
        f"{cname}={priors.get(cname, 0):.2f}"
        for cname in sorted(contributors)
    ]
    top_long = max(combined.items(), key=lambda kv: kv[1], default=("", 0.0))
    top_short = min(combined.items(), key=lambda kv: kv[1], default=("", 0.0))
    parts.append(
        f"top_long={top_long[0]}@{top_long[1]:.3f}"
        if top_long[1] > 0
        else "top_long=none"
    )
    parts.append(
        f"top_short={top_short[0]}@{top_short[1]:.3f}"
        if top_short[1] < 0
        else "top_short=none"
    )
    parts.append(f"confidence={confidence:.2f}")
    return "; ".join(parts)


__all__ = [
    "FusionInputs",
    "FusionOutput",
    "synthesize",
]
