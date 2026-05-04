from __future__ import annotations


def test_service_manager_health_aggregates_services(monkeypatch) -> None:
    from aqp.services import service_manager

    monkeypatch.setattr(service_manager, "SERVICE_NAMES", ("trino", "neo4j"))
    monkeypatch.setattr(
        service_manager,
        "service_health",
        lambda name: {"ok": name == "trino", "service": name},
    )
    monkeypatch.setattr(service_manager, "config_snapshot", lambda: {"graph_store": "neo4j"})

    payload = service_manager.health()

    assert payload["ok"] is False
    assert payload["services"]["trino"]["ok"] is True
    assert payload["services"]["neo4j"]["ok"] is False


def test_service_action_is_guarded_when_control_disabled(monkeypatch) -> None:
    from aqp.services import service_manager

    monkeypatch.setattr(service_manager.settings, "service_control_enabled", False)

    payload = service_manager.service_action("trino", "restart")

    assert payload["ok"] is False
    assert payload["enabled"] is False
    assert "AQP_SERVICE_CONTROL_ENABLED" in payload["error"]
