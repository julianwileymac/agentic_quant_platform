from __future__ import annotations


def test_visualization_config_exposes_superset_and_trino(monkeypatch) -> None:
    from aqp.api.routes import visualizations

    monkeypatch.setattr(visualizations.settings, "superset_public_url", "http://superset.local")
    monkeypatch.setattr(visualizations.settings, "trino_uri", "trino://trino@localhost:8080/iceberg")
    monkeypatch.setattr(visualizations.settings, "trino_http_url", "")

    payload = visualizations.visualization_config()

    assert payload["superset_url"] == "http://superset.local"
    assert payload["trino_uri"].startswith("trino://")
    assert payload["trino_http_url"] is None


def test_visualization_config_exposes_trino_http_url_when_set(monkeypatch) -> None:
    from aqp.api.routes import visualizations

    monkeypatch.setattr(visualizations.settings, "superset_public_url", "http://superset.local")
    monkeypatch.setattr(visualizations.settings, "trino_uri", "trino://trino@trino:8080/iceberg")
    monkeypatch.setattr(visualizations.settings, "trino_http_url", "http://trino:8080")

    payload = visualizations.visualization_config()

    assert payload["trino_http_url"] == "http://trino:8080"


def test_trino_health_returns_probe_payload(monkeypatch) -> None:
    from aqp.api.routes import visualizations

    monkeypatch.setattr(
        visualizations,
        "probe_trino_coordinator",
        lambda: {"ok": True, "coordinator_url": "http://localhost:8080", "node_version": "470"},
    )

    payload = visualizations.trino_health()

    assert payload["ok"] is True
    assert payload["node_version"] == "470"


def test_superset_guest_token_uses_default_dashboard(monkeypatch) -> None:
    from aqp.api.routes import visualizations
    from aqp.api.routes.visualizations import GuestTokenRequest

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return None

        def create_guest_token(self, *, resources, rls):  # noqa: ANN001
            assert resources == [{"type": "dashboard", "id": "dash-1"}]
            assert rls == []
            return "guest-token"

    monkeypatch.setattr(visualizations.settings, "superset_default_dashboard_uuid", "dash-1")
    monkeypatch.setattr(visualizations.settings, "superset_public_url", "http://superset.local")
    monkeypatch.setattr(visualizations, "SupersetClient", lambda: FakeClient())

    response = visualizations.superset_guest_token(GuestTokenRequest())

    assert response.token == "guest-token"
    assert response.dashboard_uuid == "dash-1"


def test_list_visualization_datasets_merges_iceberg_and_presets(monkeypatch) -> None:
    from aqp.api.routes import visualizations

    monkeypatch.setattr(
        visualizations.iceberg_catalog,
        "list_tables",
        lambda: ["aqp_equity.sp500_daily", "aqp_custom.live_only"],
    )

    payload = visualizations.list_visualization_datasets()
    identifiers = {row.identifier for row in payload["datasets"]}

    # Live Iceberg table that has no preset still appears.
    assert "aqp_custom.live_only" in identifiers
    # Preset table appears AND is marked as having_preset.
    sp500 = next(row for row in payload["datasets"] if row.identifier == "aqp_equity.sp500_daily")
    assert sp500.has_preset is True


def test_visualization_dataset_columns_404s_when_missing(monkeypatch) -> None:
    from fastapi import HTTPException

    from aqp.api.routes import visualizations

    monkeypatch.setattr(visualizations.iceberg_catalog, "load_table", lambda identifier: None)  # noqa: ARG005

    try:
        visualizations.visualization_dataset_columns("aqp_missing.table")
    except HTTPException as exc:
        assert exc.status_code == 404
    else:  # pragma: no cover - expected to raise
        raise AssertionError("expected HTTPException")


def test_visualization_dataset_columns_returns_schema(monkeypatch) -> None:
    from aqp.api.routes import visualizations

    class _FakeField:
        def __init__(self, name: str, dtype: str) -> None:
            self.name = name
            self.field_type = dtype

    class _FakeSchema:
        fields = [
            _FakeField("timestamp", "timestamp[ns]"),
            _FakeField("close", "double"),
        ]

    class _FakeTable:
        def schema(self) -> _FakeSchema:
            return _FakeSchema()

    monkeypatch.setattr(visualizations.iceberg_catalog, "load_table", lambda identifier: _FakeTable())  # noqa: ARG005

    response = visualizations.visualization_dataset_columns("aqp_equity.sp500_daily")
    names = [c.name for c in response.columns]
    assert names == ["timestamp", "close"]


def test_clear_visualization_cache_returns_summary(monkeypatch) -> None:
    from aqp.api.routes import visualizations
    from aqp.api.routes.visualizations import CacheClearRequest

    monkeypatch.setattr(visualizations, "clear_cache", lambda *, older_than_seconds=None: {"file": 3, "redis": 1})

    response = visualizations.clear_visualization_cache(CacheClearRequest(older_than_seconds=None))
    assert response.file == 3
    assert response.redis == 1
