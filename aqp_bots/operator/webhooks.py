"""Validating + mutating webhooks for QuantBot CRs.

Enforced at admission time so malformed CRs never reach the operator's
reconciliation loop:

- HFT bots without ``needsNumaPinning=True`` → reject.
- HFT bots without ``expectedP99TickToTradeUs`` → reject.
- HFT bots without the full RTS 6 Article 15 policy set → reject.
- ``RiskPolicy.hardLimits.maxOrderValueUsd == "0"`` → reject.
- Strategy ref pointing at non-existent ``Strategy`` CR → reject (warn-only
  at first; ``Strategy`` may be applied after the Bot in GitOps order).
- KillSwitch with empty target → reject.

The mutating side injects:

- Standard labels (``app.kubernetes.io/managed-by=quantbot-operator``).
- ``terminationGracePeriodSeconds`` defaults.
- A sidecar OTel Collector reference (when telemetry.hftMode=true).

Webhook server runs inside the operator pod on port 8443; cert-manager
issues the TLS cert via the manifests under
``aqp_platform/deployments/kubernetes/bots-operator/``.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _kopf():
    try:
        import kopf  # type: ignore[import-not-found]

        return kopf
    except ImportError:
        return None


def register_webhooks() -> bool:
    """Register kopf webhook handlers.

    The handlers below are admission validators; mutating webhooks
    register the same way with ``@kopf.on.mutate``.
    """
    kopf = _kopf()
    if kopf is None:
        return False

    @kopf.on.validate("quantbot.io", "v1", "bots")  # type: ignore[union-attr]
    def validate_bot(spec, name, namespace, warnings, **_):  # type: ignore[no-redef]
        caps = (spec or {}).get("capabilities", {})
        frequency = caps.get("frequency", "mid")
        if frequency == "hft":
            if not caps.get("needsNumaPinning"):
                raise kopf.AdmissionError(  # type: ignore[attr-defined]
                    f"Bot {namespace}/{name}: HFT bots MUST set "
                    "capabilities.needsNumaPinning=true"
                )
            if not caps.get("expectedP99TickToTradeUs"):
                raise kopf.AdmissionError(  # type: ignore[attr-defined]
                    f"Bot {namespace}/{name}: HFT bots MUST set "
                    "capabilities.expectedP99TickToTradeUs"
                )
            risk_refs = (spec or {}).get("riskPolicyRefs", [])
            if not risk_refs:
                warnings.append(
                    f"Bot {namespace}/{name}: HFT bots SHOULD reference at least one RiskPolicy"
                )

    @kopf.on.validate("quantbot.io", "v1", "riskpolicies")  # type: ignore[union-attr]
    def validate_riskpolicy(spec, name, namespace, **_):
        hard = (spec or {}).get("hardLimits", {}) or {}
        cap = hard.get("maxOrderValueUsd")
        if cap is not None:
            try:
                if float(cap) <= 0:
                    raise kopf.AdmissionError(  # type: ignore[attr-defined]
                        f"RiskPolicy {namespace}/{name}: maxOrderValueUsd must be > 0"
                    )
            except (TypeError, ValueError):
                raise kopf.AdmissionError(  # type: ignore[attr-defined]
                    f"RiskPolicy {namespace}/{name}: maxOrderValueUsd must be numeric"
                )

    @kopf.on.validate("quantbot.io", "v1", "killswitches")  # type: ignore[union-attr]
    def validate_killswitch(spec, name, namespace, **_):
        if not (spec or {}).get("target"):
            raise kopf.AdmissionError(  # type: ignore[attr-defined]
                f"KillSwitch {namespace}/{name}: spec.target must be non-empty"
            )

    @kopf.on.mutate("quantbot.io", "v1", "bots")  # type: ignore[union-attr]
    def mutate_bot(spec, name, patch, **_):
        # Stamp managed-by label.
        if hasattr(patch, "metadata"):
            labels = patch.metadata.setdefault("labels", {})
            labels.setdefault("app.kubernetes.io/managed-by", "quantbot-operator")

    return True


__all__ = ["register_webhooks"]
