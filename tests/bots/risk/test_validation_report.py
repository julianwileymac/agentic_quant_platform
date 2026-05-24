"""Phase 5: RTS 6 Art. 9 / 15c3-5(e) annual validation report shape."""
from __future__ import annotations

from aqp_bots.risk.reg.validation_report import generate_validation_report


def test_report_has_required_sections() -> None:
    report = generate_validation_report(bot_inventory=[{"slug": "test-bot", "fleet": "f1", "kind": "trading"}])
    assert report["api_version"] == "quantbot.io/v1"
    assert report["kind"] == "ValidationReport"
    section_names = {s["name"] for s in report["sections"]}
    assert "MiFID II RTS 6" in section_names
    assert "SEC Rule 15c3-5" in section_names


def test_report_includes_attestation_slots() -> None:
    report = generate_validation_report()
    att = report["attestations"]
    assert "risk_management_function" in att
    assert "internal_audit" in att
    assert "ceo_certification" in att
    # All attestation slots start unsigned — operators fill them in.
    assert att["risk_management_function"]["drafted_at"] is None
    assert att["internal_audit"]["audited_at"] is None
    assert att["ceo_certification"]["signed_at"] is None


def test_report_carries_bot_inventory() -> None:
    inventory = [{"slug": "a", "fleet": "f1"}, {"slug": "b", "fleet": "f2"}]
    report = generate_validation_report(bot_inventory=inventory)
    assert report["scope"]["bot_count"] == 2
    assert "f1" in report["scope"]["fleets"]
    assert "f2" in report["scope"]["fleets"]
