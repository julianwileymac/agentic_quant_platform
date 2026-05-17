"""Hermetic tests for the source setup wizards registry."""
from __future__ import annotations


def test_wizard_catalog_present() -> None:
    from aqp.data.sources.setup_wizards import WIZARDS, get_wizard, list_wizards

    assert "alpha_vantage" in WIZARDS
    assert "fred" in WIZARDS
    assert get_wizard("ALPHA_VANTAGE").source_key == "alpha_vantage"
    names = {w.source_key for w in list_wizards()}
    assert {"alpha_vantage", "fred", "sec_edgar", "gdelt", "airbyte"} <= names


def test_wizard_step_runner_returns_step_result(monkeypatch) -> None:
    from aqp.data.sources.setup_wizards import get_wizard

    wizard = get_wizard("alpha_vantage")
    assert wizard is not None
    monkeypatch.setenv("AQP_ALPHA_VANTAGE_API_KEY", "test-key")
    result = wizard.run_step("credentials", {"AQP_ALPHA_VANTAGE_API_KEY": "test-key"})
    assert result.ok is True
    assert "configured" in result.message


def test_wizard_step_missing_credential_fails(monkeypatch) -> None:
    from aqp.data.sources.setup_wizards import get_wizard

    monkeypatch.delenv("AQP_FRED_API_KEY", raising=False)
    wizard = get_wizard("fred")
    result = wizard.run_step("credentials", {})
    assert result.ok is False
    assert "missing" in result.message
