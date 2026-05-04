from __future__ import annotations

from aqp.visualization.superset_assets import build_asset_plan, common_dataset_identifiers


def test_asset_plan_filters_to_available_common_datasets() -> None:
    plan = build_asset_plan(available_identifiers=["aqp_equity.sp500_daily"])

    assert plan.database["database_name"] == "AQP Trino Iceberg"
    assert [dataset.identifier for dataset in plan.datasets] == ["aqp_equity.sp500_daily"]
    assert plan.charts
    assert plan.dashboards[0].slug == "aqp-market-data-explorer"


def test_asset_plan_emits_multiple_charts_for_price_dataset() -> None:
    plan = build_asset_plan(available_identifiers=["aqp_equity.sp500_daily"])

    sp500_charts = [c for c in plan.charts if c.datasource_identifier == "aqp_equity.sp500_daily"]
    # Price category emits Close + Volume + Latest Bars (3 charts).
    assert len(sp500_charts) >= 2
    viz_types = {c.viz_type for c in sp500_charts}
    assert {"echarts_timeseries_line", "table"}.issubset(viz_types)


def test_asset_plan_routes_macro_to_macro_factory() -> None:
    plan = build_asset_plan(available_identifiers=["aqp_macro.fred_basket"])

    macro = [c for c in plan.charts if c.datasource_identifier == "aqp_macro.fred_basket"]
    assert macro
    assert all(c.viz_type == "echarts_timeseries_line" for c in macro)
    # Macro factory groups by series_id, not vt_symbol.
    assert macro[0].params.get("groupby") == ["series_id"]


def test_asset_plan_excludes_unavailable_datasets() -> None:
    plan = build_asset_plan(available_identifiers=[])

    assert plan.datasets == []
    assert plan.charts == []
    # Dashboard shell still gets emitted so the slug is stable.
    assert plan.dashboards[0].slug == "aqp-market-data-explorer"


def test_common_dataset_identifiers_are_namespaced() -> None:
    identifiers = common_dataset_identifiers()
    assert identifiers
    for identifier in identifiers:
        assert "." in identifier, f"{identifier!r} must be 'namespace.table'"
        # Namespaces should follow the aqp_<source> convention.
        namespace, _, _ = identifier.partition(".")
        assert namespace.startswith("aqp_") or namespace == "aqp"
