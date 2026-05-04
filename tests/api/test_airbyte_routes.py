from __future__ import annotations


def test_airbyte_health_when_disabled(monkeypatch) -> None:
    from aqp.api.routes import airbyte

    monkeypatch.setattr(airbyte.settings, "airbyte_enabled", False)
    monkeypatch.setattr(airbyte.settings, "airbyte_base_url", "http://example.invalid:8001")

    payload = airbyte.health()

    assert payload["ok"] is False
    assert payload["enabled"] is False
    assert payload["airbyte"]["reachable"] is False
    assert "AQP_AIRBYTE_ENABLED" in payload["airbyte"]["detail"]
