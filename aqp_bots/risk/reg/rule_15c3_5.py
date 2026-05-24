"""SEC Rule 15c3-5 (17 CFR § 240.15c3-5) crosswalk.

Maps the financial / regulatory pre-trade controls from § 240.15c3-5(c)(1)
onto policy classes. Per § 240.15c3-5(d) the controls must be "under
the direct and exclusive control of the broker or dealer" — this is
why the platform additionally runs an out-of-band risk service
(:mod:`aqp_bots.risk.service`) in addition to the in-bot fast path.

ENGINEERING CROSSWALK ONLY — see plan caveat #5.
"""
from __future__ import annotations

RULE_15C3_5_C1_MAPPING: dict[str, str] = {
    "PriceCollarPolicy": (
        "15c3-5 (c)(1)(i) — financial risk: prevent entry of orders that exceed "
        "appropriate pre-set credit or capital thresholds (price collar component)"
    ),
    "MaxOrderValuePolicy": (
        "15c3-5 (c)(1)(i) — financial risk: prevent entry of orders that exceed "
        "appropriate pre-set credit or capital thresholds (per-order value)"
    ),
    "MaxOrderVolumePolicy": (
        "15c3-5 (c)(1)(i) — financial risk: prevent entry of erroneous orders "
        "(per-order volume)"
    ),
    "BuyingPowerPolicy": (
        "15c3-5 (c)(1)(i) — financial risk: aggregate credit/capital management"
    ),
    "InstrumentAllowlistPolicy": (
        "15c3-5 (c)(1)(ii) — regulatory risk: prevent entry of orders that fail "
        "to comply with regulatory requirements (instrument permission)"
    ),
    "FatFingerPolicy": (
        "15c3-5 (c)(1)(i) — financial risk: prevent entry of erroneous orders "
        "(fat-finger pattern)"
    ),
}


# Section (d) — direct and exclusive control of the broker.
RULE_15C3_5_D_NOTE = (
    "17 CFR § 240.15c3-5(d): the financial risk management controls and supervisory "
    "procedures required by this section shall be under the direct and exclusive "
    "control of the broker or dealer. The QuantBot Platform satisfies this by running "
    "the layer-2 pre-trade risk service as a separate Kubernetes Deployment owned by "
    "the broker-dealer ServiceAccount; the in-bot layer-1 engine is for latency-sensitive "
    "fast-path screening and does not relieve the broker-dealer of layer-2 obligations."
)


# Section (e) — annual review + CEO certification.
RULE_15C3_5_E_NOTE = (
    "17 CFR § 240.15c3-5(e): the broker or dealer shall regularly review the effectiveness "
    "of the risk management controls and supervisory procedures … and the CEO shall "
    "certify annually that the firm's risk management controls and supervisory procedures "
    "comply with paragraphs (b) and (c) of this section. The platform produces the annual "
    "validation report via aqp_bots.risk.reg.validation_report.generate_validation_report; "
    "CEO sign-off is operational, not generated."
)


__all__ = [
    "RULE_15C3_5_C1_MAPPING",
    "RULE_15C3_5_D_NOTE",
    "RULE_15C3_5_E_NOTE",
]
