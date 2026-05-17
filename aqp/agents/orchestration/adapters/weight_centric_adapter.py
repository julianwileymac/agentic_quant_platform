"""``WeightCentricExecutionAdapter`` — fusion -> risk-aware target weights.

Reads ``state["fusion_output"]`` (populated by the Phase 4
:class:`SignalFusionAdapter`) and pushes the per-symbol weight vector
through :class:`aqp.rl.portfolio.pipeline.WeightCentricPipeline` so
the final target weights ride the existing
:class:`aqp.rl.portfolio.risk_overlay.RiskOverlay` + the production
:class:`aqp.risk.limits.RiskLimits`. This honours hard rule 38:

> All weight-centric portfolio actions go through the FinRL-X
> four-stage pipeline ``f_S -> f_A -> f_T -> f_R``.

The adapter NEVER produces a :class:`aqp.core.types.SignalEvent`
itself — that's the existing
:func:`aqp.agents.graph.builder._emit_signal_event_node`'s job. We
simply stamp the final ``target_weights`` slot so the downstream
emit node sees the risk-overlaid vector instead of the raw fusion
output. The existing risk-simulator approval predicate
(:func:`aqp.agents.graph.conditions.risk_simulator_approves`) stays
authoritative.

Gated by ``settings.orchestration_fusion_enabled`` (the same flag
guards both fusion + weight-centric — they are designed to ship as
a pair).
"""
from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np

from aqp.agents.orchestration.base import OrchestrationAdapter
from aqp.agents.orchestration.types import (
    AdapterContext,
    AdapterFailure,
    AdapterResult,
)
from aqp.config import settings

logger = logging.getLogger(__name__)


class WeightCentricExecutionAdapter(OrchestrationAdapter):
    """Bridge fusion output -> :class:`WeightCentricPipeline`.

    Spec contract::

        adapter: WeightCentricExecutionAdapter
        params:
          universe: ["AAPL.US", "MSFT.US", "..."]   # optional override
          context: {turbulence: 0.0, equity: 1e6}   # forwarded into pipeline.context
          max_position_pct: 0.20                    # optional cap override
          max_gross_exposure: 1.0                   # optional cap override

    State input slots:

    - ``fusion_output.target_weights`` (vt_symbol -> weight)
    - ``inputs.universe`` (fallback for the universe)

    State output slots:

    - ``target_weights`` (final post-overlay weight dict)
    - ``weight_pipeline_history`` (per-stage f_S/f_A/f_T/f_R snapshots)
    - ``risk_veto`` (set when the overlay reduced gross exposure below
      the policy threshold; downstream emit_signal_event reads this)
    """

    adapter_kind = "execution"
    adapter_alias = "WeightCentricExecutionAdapter"
    adapter_source = "finrl"
    adapter_category = "execution"
    adapter_tags = ("weight_centric", "risk_overlay", "finrl_x")

    def invoke(self, state: Any, context: AdapterContext) -> AdapterResult:
        start = time.perf_counter()
        if not getattr(settings, "orchestration_fusion_enabled", False):
            return AdapterResult(
                state=state,
                status=AdapterResult.STATUS_ERROR,
                failure=AdapterFailure(
                    message=(
                        "WeightCentricExecutionAdapter requires "
                        "AQP_ORCHESTRATION_FUSION_ENABLED=true"
                    ),
                    kind="policy",
                ),
                duration_ms=(time.perf_counter() - start) * 1000.0,
            )

        params = context.extras.get("params") or {}
        fusion_output = (state or {}).get("fusion_output") or {}
        target_weights = dict(fusion_output.get("target_weights") or {})

        if not target_weights and not (state or {}).get("target_weights"):
            return AdapterResult(
                state=state,
                status=AdapterResult.STATUS_ERROR,
                failure=AdapterFailure(
                    message=(
                        "no fusion_output.target_weights — run SignalFusionAdapter first"
                    ),
                    kind="error",
                ),
                duration_ms=(time.perf_counter() - start) * 1000.0,
            )

        if not target_weights:
            target_weights = dict((state or {}).get("target_weights") or {})

        universe = list(
            params.get("universe")
            or (state or {}).get("universe")
            or (state or {}).get("inputs", {}).get("universe")
            or sorted(target_weights.keys())
        )
        # The pipeline's raw_action is a numpy vector aligned with the
        # universe. Missing symbols (e.g. fusion produced none for that
        # asset) default to zero weight.
        raw_action = np.asarray(
            [float(target_weights.get(sym, 0.0)) for sym in universe],
            dtype=np.float64,
        )

        try:
            from aqp.rl.portfolio.pipeline import WeightCentricPipeline
            from aqp.rl.portfolio.risk_overlay import (
                GrossExposureRiskOverlay,
                PositionCapRiskOverlay,
                StackedRiskOverlay,
            )
            from aqp.risk.limits import RiskLimits
        except Exception as exc:  # noqa: BLE001
            logger.exception("WeightCentricExecutionAdapter import failed")
            return AdapterResult(
                state=state,
                status=AdapterResult.STATUS_ERROR,
                failure=AdapterFailure(
                    message=f"pipeline import failed: {exc}", kind="error"
                ),
                duration_ms=(time.perf_counter() - start) * 1000.0,
            )

        # Build the risk overlay from the spec-provided caps + production
        # defaults. Adapters override per-spec; missing fields fall back
        # to RiskLimits defaults so live and backtest paths stay in sync.
        # Order matters: position cap fires BEFORE gross scaling so an
        # oversized position can't consume the entire gross budget via
        # pure normalisation.
        limits = RiskLimits()
        max_position = float(
            params.get("max_position_pct") or limits.max_position_pct
        )
        max_gross = float(
            params.get("max_gross_exposure") or limits.max_gross_exposure
        )
        overlay = StackedRiskOverlay(
            overlays=[
                PositionCapRiskOverlay(max_position_pct=max_position),
                GrossExposureRiskOverlay(max_gross=max_gross),
            ]
        )

        pipeline = WeightCentricPipeline(risk_overlay=overlay)
        pipeline_context = dict(params.get("context") or {})
        pipeline_context.setdefault("equity", 1.0)
        pipeline_context.setdefault("turbulence", 0.0)

        try:
            pipeline_state = pipeline.run(
                universe=universe,
                raw_action=raw_action,
                context=pipeline_context,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("WeightCentricPipeline.run failed")
            return AdapterResult(
                state=state,
                status=AdapterResult.STATUS_ERROR,
                failure=AdapterFailure(message=str(exc), kind="error"),
                duration_ms=(time.perf_counter() - start) * 1000.0,
            )

        post = pipeline_state.weights
        post_weights = (
            {
                sym: float(post[i])
                for i, sym in enumerate(pipeline_state.universe)
                if i < len(post)
            }
            if post is not None
            else {}
        )

        merged = dict(state)
        prior_gross = sum(abs(v) for v in raw_action)
        post_gross = sum(abs(v) for v in post_weights.values())
        veto = bool(prior_gross > 0 and post_gross < prior_gross * 0.5)

        merged["target_weights"] = post_weights
        merged["weight_pipeline_history"] = [
            {"stage": stage, "weights": vec.tolist()}
            for stage, vec in (pipeline_state.history or [])
        ]
        merged["risk_veto"] = veto
        if veto:
            # Mirror the existing risk_simulator_approves contract so
            # downstream emit_signal_event short-circuits.
            existing_verdict = dict(merged.get("simulation_verdict") or {})
            existing_verdict.setdefault("approved", False)
            existing_verdict.setdefault(
                "risk_breaches", []
            )
            if "risk_overlay_veto" not in existing_verdict["risk_breaches"]:
                existing_verdict["risk_breaches"] = list(
                    existing_verdict["risk_breaches"]
                ) + ["risk_overlay_veto"]
            existing_verdict["rationale"] = (
                f"risk overlay reduced gross exposure from {prior_gross:.3f} "
                f"to {post_gross:.3f}; vetoing emit"
            )
            merged["simulation_verdict"] = existing_verdict

        breadcrumb = {
            "adapter": self.adapter_alias,
            "node": "weight_centric_pipeline",
            "status": "ok",
            "duration_ms": round((time.perf_counter() - start) * 1000.0, 3),
            "prior_gross": round(float(prior_gross), 4),
            "post_gross": round(float(post_gross), 4),
            "risk_veto": veto,
        }
        existing_breadcrumbs = list(merged.get("adapter_breadcrumbs") or [])
        merged["adapter_breadcrumbs"] = existing_breadcrumbs + [breadcrumb]
        return AdapterResult(
            state=merged,
            status=AdapterResult.STATUS_COMPLETED,
            breadcrumbs=[breadcrumb],
            duration_ms=(time.perf_counter() - start) * 1000.0,
        )


__all__ = ["WeightCentricExecutionAdapter"]
