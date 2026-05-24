"""Regulatory crosswalk for the pre-trade risk layer.

These modules are **engineering crosswalks**, not legal advice (see
plan caveat #5). The annual validation report (RTS 6 Art. 9) requires
legal/compliance sign-off and a CEO attestation; the helpers here let
us *generate* the artifact mechanically but do not certify it.
"""
from __future__ import annotations

from aqp_bots.risk.reg.conformance import run_conformance_tests
from aqp_bots.risk.reg.rts6 import (
    RTS6_ART_15_MAPPING,
    rts6_required_policies,
)
from aqp_bots.risk.reg.rule_15c3_5 import RULE_15C3_5_C1_MAPPING
from aqp_bots.risk.reg.stress import run_stress_test
from aqp_bots.risk.reg.validation_report import generate_validation_report

__all__ = [
    "RTS6_ART_15_MAPPING",
    "RULE_15C3_5_C1_MAPPING",
    "generate_validation_report",
    "run_conformance_tests",
    "rts6_required_policies",
    "run_stress_test",
]
