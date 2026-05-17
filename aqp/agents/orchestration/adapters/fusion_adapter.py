"""``SignalFusionAdapter`` — deterministic fusion node for workflows.

Reads the upstream-populated slots on the orchestration state
(``proposed_alpha``, ``simulation_verdict``, ``bull_argument``,
``bear_argument``, ``debate_verdict``, plus any ``quant_signals`` /
``model_predictions`` placed there by earlier nodes), packages them
into a :class:`aqp.agents.trading.fusion.FusionInputs`, calls
:func:`aqp.agents.trading.fusion.synthesize`, and writes the
:class:`FusionOutput` back to ``state["fusion_output"]`` (with the
inputs preserved under ``state["fusion_inputs"]`` for the audit hook
``data.orchestration.fusion_inputs_for_run``).

The adapter is **deterministic + read-only** with respect to the
production primitives — it never:

- calls ``router_complete`` (rule 12),
- writes to Iceberg (rule 3),
- imports ORM models (rule 22),
- publishes to Redis outside the standard ``_progress.emit`` path
  (rule 4 — the Phase 2 ``WorkflowRuntime`` handles emits, not the
  adapter itself).

Gated by ``settings.orchestration_fusion_enabled``; with the flag off
the adapter still registers (so the studio dropdown lists it) but
:meth:`invoke` short-circuits to a policy-style failure.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from aqp.agents.orchestration.base import OrchestrationAdapter
from aqp.agents.orchestration.types import (
    AdapterContext,
    AdapterFailure,
    AdapterResult,
)
from aqp.agents.trading.fusion import FusionInputs, synthesize
from aqp.config import settings

logger = logging.getLogger(__name__)


class SignalFusionAdapter(OrchestrationAdapter):
    """Deterministic combine of debate / quant / model contributors.

    Spec contract::

        adapter: SignalFusionAdapter
        params:
          weights_prior:                # optional per-contributor prior
            debate: 0.5
            quant:  0.3
            model:  0.2
          model_confidence: 0.6          # optional scalar in [0, 1]
          risk_overlay:                  # optional caps applied at fusion time
            max_position_pct: 0.10
            max_gross_exposure: 1.0
    """

    adapter_kind = "fusion"
    adapter_alias = "SignalFusionAdapter"
    adapter_source = "vibe_trading"
    adapter_category = "fusion"
    adapter_tags = ("deterministic", "weight_vector", "fusion")

    def invoke(self, state: Any, context: AdapterContext) -> AdapterResult:
        start = time.perf_counter()
        if not getattr(settings, "orchestration_fusion_enabled", False):
            return AdapterResult(
                state=state,
                status=AdapterResult.STATUS_ERROR,
                failure=AdapterFailure(
                    message=(
                        "SignalFusionAdapter requires "
                        "AQP_ORCHESTRATION_FUSION_ENABLED=true"
                    ),
                    kind="policy",
                ),
                duration_ms=(time.perf_counter() - start) * 1000.0,
            )

        params = context.extras.get("params") or {}
        inputs = self._collect_inputs(state, params)
        try:
            output = synthesize(inputs)
        except Exception as exc:  # noqa: BLE001
            logger.exception("SignalFusionAdapter synth failed")
            return AdapterResult(
                state=state,
                status=AdapterResult.STATUS_ERROR,
                failure=AdapterFailure(message=str(exc), kind="error"),
                duration_ms=(time.perf_counter() - start) * 1000.0,
            )

        merged = dict(state)
        merged["fusion_inputs"] = inputs.to_dict()
        merged["fusion_output"] = output.to_dict()
        merged["target_weights"] = dict(output.target_weights)
        breadcrumb = {
            "adapter": self.adapter_alias,
            "node": "fusion_synth",
            "status": "ok",
            "duration_ms": round((time.perf_counter() - start) * 1000.0, 3),
            "n_symbols": len(output.target_weights),
            "confidence": round(output.confidence, 4),
        }
        existing_breadcrumbs = list(merged.get("adapter_breadcrumbs") or [])
        merged["adapter_breadcrumbs"] = existing_breadcrumbs + [breadcrumb]
        return AdapterResult(
            state=merged,
            status=AdapterResult.STATUS_COMPLETED,
            breadcrumbs=[breadcrumb],
            duration_ms=(time.perf_counter() - start) * 1000.0,
        )

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _collect_inputs(state: Any, params: dict[str, Any]) -> FusionInputs:
        quant_signals = dict((state or {}).get("quant_signals") or {})
        model_predictions = dict((state or {}).get("model_predictions") or {})
        # Prefer the explicit debate verdict slot; fall back to the older
        # ``simulation_verdict`` / ``trader_signal`` slots so workflows that
        # ran without an explicit debate adapter still produce fusion output.
        debate_verdict = (
            (state or {}).get("debate_verdict")
            or (state or {}).get("simulation_verdict")
            or (state or {}).get("trader_signal")
            or {}
        )
        if not isinstance(debate_verdict, dict):
            debate_verdict = {}
        return FusionInputs(
            quant_signals=quant_signals,
            debate_verdict=dict(debate_verdict),
            model_predictions=model_predictions,
            model_confidence=params.get("model_confidence"),
            risk_overlay=dict(params.get("risk_overlay") or {}),
            weights_prior=dict(params.get("weights_prior") or {}),
        )


__all__ = ["SignalFusionAdapter"]
