from __future__ import annotations


def test_trino_coordinator_http_url_from_explicit_setting(monkeypatch) -> None:
    from aqp.services import trino_probe

    monkeypatch.setattr(trino_probe.settings, "trino_http_url", "http://custom:9999/")
    monkeypatch.setattr(trino_probe.settings, "trino_uri", "trino://u@ignored:8080/iceberg")

    assert trino_probe.trino_coordinator_http_url() == "http://custom:9999"


def test_trino_coordinator_http_url_from_trino_uri(monkeypatch) -> None:
    from aqp.services import trino_probe

    monkeypatch.setattr(trino_probe.settings, "trino_http_url", "")
    monkeypatch.setattr(trino_probe.settings, "trino_uri", "trino://trino@coordinator:8443/iceberg")

    assert trino_probe.trino_coordinator_http_url() == "http://coordinator:8443"


def test_trino_coordinator_http_url_empty_when_no_uri(monkeypatch) -> None:
    from aqp.services import trino_probe

    monkeypatch.setattr(trino_probe.settings, "trino_http_url", "")
    monkeypatch.setattr(trino_probe.settings, "trino_uri", "")

    assert trino_probe.trino_coordinator_http_url() == ""
