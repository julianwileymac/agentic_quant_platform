"""MiFID II RTS 6 (Commission Delegated Regulation (EU) 2017/589) crosswalk.

Maps every required pre-trade control from Article 15(1)/(3)/(5) and
the kill-functionality requirement of Article 12 onto a concrete
policy class in :mod:`aqp_bots.risk.policies`.

ENGINEERING CROSSWALK ONLY — see plan caveat #5.
"""
from __future__ import annotations

# Required-policy mapping. Keys are the policy class names from
# :mod:`aqp_bots.risk.policies`; values are the citation strings used
# in audit / validation reports.
RTS6_ART_15_MAPPING: dict[str, str] = {
    "PriceCollarPolicy": (
        "RTS 6 Article 15(1)(a) — price collars "
        "(automatically block or cancel orders that do not meet set price parameters)"
    ),
    "MaxOrderValuePolicy": (
        "RTS 6 Article 15(1)(b) — maximum order values "
        "(prevent orders with an uncommonly large order value)"
    ),
    "MaxOrderVolumePolicy": (
        "RTS 6 Article 15(1)(c) — maximum order volumes "
        "(prevent orders with an uncommonly large order size)"
    ),
    "MaxMessagesPerSecondPolicy": (
        "RTS 6 Article 15(1)(d) — maximum messages limit "
        "(prevent excessive submission/modification/cancellation messages)"
    ),
    "RepeatedExecutionThrottlePolicy": (
        "RTS 6 Article 15(3) — repeated-execution throttle "
        "(prevent repeated execution of the same algorithm)"
    ),
    "InstrumentAllowlistPolicy": (
        "RTS 6 Article 15(5) — permission to trade an instrument"
    ),
}


# Other RTS 6 controls handled outside the policy framework.
RTS6_OTHER_CONTROLS: dict[str, str] = {
    "kill_switch_v2": "RTS 6 Article 12 — kill functionality",
    "reconciliation_real_time": "RTS 6 Article 17(3) — real-time reconciliation",
    "alert_window_5s": "RTS 6 Article 16(5) — alerts within 5 seconds",
    "conformance_testing": "RTS 6 Article 6 — conformance testing",
    "stress_testing": "RTS 6 Article 10 — stress testing (2x prior 6mo peak)",
    "validation_report": "RTS 6 Article 9 — annual self-assessment + validation report",
}


def rts6_required_policies() -> list[str]:
    """Return the canonical list of RTS 6 Art. 15 policies an HFT bot
    MUST have configured.

    The operator's validating webhook rejects any ``Bot`` CR whose
    ``capabilities.frequency=hft`` and whose ``risk_layer.layer1_policies``
    doesn't cover every name in this list.
    """
    return list(RTS6_ART_15_MAPPING.keys()) + ["VolatilityCircuitBreakerPolicy"]


__all__ = [
    "RTS6_ART_15_MAPPING",
    "RTS6_OTHER_CONTROLS",
    "rts6_required_policies",
]
