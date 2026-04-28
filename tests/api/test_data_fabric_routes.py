from __future__ import annotations


def test_fabric_overview_returns_summary(monkeypatch):
    from aqp.api.routes import data as data_route

    monkeypatch.setattr(
        "aqp.data.sources.registry.list_data_sources",
        lambda: [
            {
                "name": "alpha_vantage",
                "display_name": "Alpha Vantage",
                "kind": "rest_api",
                "vendor": "Alpha Vantage",
                "enabled": True,
                "capabilities": {"domains": ["market.bars", "fundamentals.overview"]},
            }
        ],
        raising=False,
    )

    monkeypatch.setattr("aqp.data.iceberg_catalog.list_namespaces", lambda: ["aqp_alpha_vantage"], raising=False)
    monkeypatch.setattr(
        "aqp.data.iceberg_catalog.list_tables",
        lambda *args, **kwargs: ["aqp_alpha_vantage.time_series_daily_adjusted"],
        raising=False,
    )

    class _FakeSession:
        def execute(self, *args, **kwargs):  # noqa: ARG002
            class _Result:
                def scalar_one(self_inner):
                    return 0

                def scalars(self_inner):
                    class _S:
                        def all(self_inner_inner):
                            return []

                    return _S()

            return _Result()

    class _SessionCtx:
        def __enter__(self_inner):
            return _FakeSession()

        def __exit__(self_inner, *exc):  # noqa: ARG002
            return False

    monkeypatch.setattr(data_route, "get_session", lambda: _SessionCtx())

    payload = data_route.fabric_overview()
    assert payload["namespaces"] == ["aqp_alpha_vantage"]
    assert payload["table_count"] >= 1
    assert payload["sources"][0]["name"] == "alpha_vantage"
    assert payload["alpha_vantage_endpoints"]
    assert payload["alpha_vantage_endpoints"][0]["iceberg_identifier"].startswith("aqp_alpha_vantage.")


def test_alpha_vantage_function_state_round_trip(monkeypatch):
    from aqp.data.sources.alpha_vantage import endpoint_state as state_mod

    monkeypatch.setattr(state_mod, "_read_meta_state", lambda fn: None)
    captured: dict[str, str] = {}

    def _write(fn, state):
        captured["state"] = dict(state)
        captured["function_id"] = fn.id

    monkeypatch.setattr(state_mod, "_write_meta_state", _write)

    state_mod.set_state(
        "timeseries.daily_adjusted",
        enabled_for_bulk=False,
        cache_ttl_seconds=120.0,
    )
    assert captured["function_id"] == "timeseries.daily_adjusted"
    assert captured["state"]["enabled_for_bulk"] is False
    assert captured["state"]["cache_ttl_seconds"] == 120.0
