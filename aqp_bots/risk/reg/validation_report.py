"""RTS 6 Article 9 + 15c3-5(e) annual validation report generator.

Generates a YAML artifact summarising:

- Every policy attached to every active bot
- The mapping of each policy onto its RTS 6 / 15c3-5 citation
- The results of the most recent conformance + stress tests
- The kill-switch drill history (quarterly per blueprint caveat #7)
- CEO + risk-management + internal audit attestation slots
  (left blank by the generator; filled by operators / officers)

The report MUST be signed off by:

- Risk management function (Art. 9(2)): drafts the report
- Internal audit (Art. 9(3)): audits the report
- CEO or equivalent (15c3-5(e)): annual certification

Generation is mechanical; sign-off is operational.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from aqp_bots.risk.reg.rts6 import RTS6_ART_15_MAPPING, RTS6_OTHER_CONTROLS
from aqp_bots.risk.reg.rule_15c3_5 import (
    RULE_15C3_5_C1_MAPPING,
    RULE_15C3_5_D_NOTE,
    RULE_15C3_5_E_NOTE,
)


@dataclass(slots=True)
class ValidationReportSection:
    name: str
    description: str
    citations: list[str] = field(default_factory=list)
    findings: dict[str, Any] = field(default_factory=dict)


def generate_validation_report(
    *,
    bot_inventory: list[dict[str, Any]] | None = None,
    conformance_results: dict[str, Any] | None = None,
    stress_results: dict[str, Any] | None = None,
    kill_switch_drills: list[dict[str, Any]] | None = None,
    reporting_period: str | None = None,
) -> dict[str, Any]:
    """Generate the validation-report payload.

    ``bot_inventory`` is a list of ``{slug, fleet, policies, frequency,
    asset_classes}`` dicts; the caller normally builds it via
    :func:`aqp_bots.registry.list_bot_specs`.
    """
    now = datetime.now(timezone.utc)
    period = reporting_period or f"FY{now.year - 1}"

    rts6 = ValidationReportSection(
        name="MiFID II RTS 6",
        description=(
            "Commission Delegated Regulation (EU) 2017/589 - Regulatory "
            "Technical Standards on the organisational requirements of investment "
            "firms engaged in algorithmic trading."
        ),
        citations=[
            "Article 6 - conformance testing",
            "Article 9 - annual self-assessment + validation report",
            "Article 10 - stress testing (2x prior 6mo peak)",
            "Article 12 - kill functionality",
            "Article 15(1) - pre-trade controls",
            "Article 15(3) - repeated-execution throttle",
            "Article 15(5) - permission to trade instrument",
            "Article 16(5) - real-time alerts within 5 seconds",
            "Article 17(3) - real-time reconciliation",
        ],
        findings={
            "art_15_policy_coverage": dict(RTS6_ART_15_MAPPING),
            "other_controls": dict(RTS6_OTHER_CONTROLS),
        },
    )

    sec = ValidationReportSection(
        name="SEC Rule 15c3-5",
        description=(
            "17 CFR § 240.15c3-5 - Risk management controls for brokers or dealers "
            "with market access."
        ),
        citations=[
            "§ 240.15c3-5(c)(1)(i) - financial risk pre-trade controls",
            "§ 240.15c3-5(c)(1)(ii) - regulatory risk pre-trade controls",
            "§ 240.15c3-5(d) - direct and exclusive broker-dealer control",
            "§ 240.15c3-5(e) - annual CEO certification",
        ],
        findings={
            "policy_coverage": dict(RULE_15C3_5_C1_MAPPING),
            "broker_dealer_control_note": RULE_15C3_5_D_NOTE,
            "annual_certification_note": RULE_15C3_5_E_NOTE,
        },
    )

    return {
        "api_version": "quantbot.io/v1",
        "kind": "ValidationReport",
        "metadata": {
            "generated_at": now.isoformat(),
            "reporting_period": period,
            "platform_version": "aqp_bots/0.2.0",
        },
        "scope": {
            "bot_count": len(bot_inventory or []),
            "fleets": sorted({b.get("fleet", "") for b in bot_inventory or [] if b.get("fleet")}),
        },
        "sections": [_to_dict(rts6), _to_dict(sec)],
        "evidence": {
            "bot_inventory": bot_inventory or [],
            "conformance_results": conformance_results or {},
            "stress_results": stress_results or {},
            "kill_switch_drills": kill_switch_drills or [],
        },
        "attestations": {
            "risk_management_function": {
                "drafted_by": None,
                "drafted_at": None,
                "notes": "Required per RTS 6 Article 9(2). To be filled by Head of Risk.",
            },
            "internal_audit": {
                "audited_by": None,
                "audited_at": None,
                "notes": "Required per RTS 6 Article 9(3). To be filled by Head of Internal Audit.",
            },
            "ceo_certification": {
                "ceo_signature": None,
                "signed_at": None,
                "notes": (
                    "Required per 17 CFR § 240.15c3-5(e). CEO certifies that "
                    "the firm's risk management controls and supervisory procedures "
                    "comply with paragraphs (b) and (c) of the rule."
                ),
            },
        },
    }


def _to_dict(section: ValidationReportSection) -> dict[str, Any]:
    return {
        "name": section.name,
        "description": section.description,
        "citations": list(section.citations),
        "findings": dict(section.findings),
    }


__all__ = ["ValidationReportSection", "generate_validation_report"]
