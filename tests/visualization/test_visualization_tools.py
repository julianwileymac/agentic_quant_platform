"""Tests for the Bokeh + Superset agent tools."""
from __future__ import annotations

import json
from typing import Any


def test_bokeh_chart_tool_returns_compact_payload(monkeypatch) -> None:
    from aqp.agents.tools.visualization_tools import BokehChartTool
    from aqp.visualization import bokeh_renderer

    captured: dict[str, Any] = {}

    def fake_render(spec):  # noqa: ANN001
        captured["spec"] = spec
        return {
            "doc": "doc-123",
            "version": "3.6.3",
            "target_id": "plot-x",
            "cache_key": "abc-001",
            "root_id": "root-1",
        }

    monkeypatch.setattr(bokeh_renderer, "render_bokeh_item", fake_render)

    tool = BokehChartTool()
    raw = tool._run(
        dataset_identifier="aqp_equity.sp500_daily",
        kind="line",
        x="timestamp",
        y="close",
        groupby="vt_symbol",
        limit=500,
        title="SPY Daily",
    )
    payload = json.loads(raw)

    assert payload["cache_key"] == "abc-001"
    assert payload["dataset_identifier"] == "aqp_equity.sp500_daily"
    assert payload["kind"] == "line"
    assert captured["spec"].limit == 500
    assert captured["spec"].title == "SPY Daily"


def test_bokeh_chart_tool_returns_error_dict_on_failure(monkeypatch) -> None:
    from aqp.agents.tools.visualization_tools import BokehChartTool
    from aqp.visualization import bokeh_renderer

    def boom(spec):  # noqa: ANN001, ARG001
        raise RuntimeError("dataset not found")

    monkeypatch.setattr(bokeh_renderer, "render_bokeh_item", boom)

    raw = BokehChartTool()._run(dataset_identifier="missing.table")
    assert json.loads(raw) == {"error": "dataset not found"}


def test_superset_dashboard_tool_returns_error_when_no_uuid(monkeypatch) -> None:
    from aqp.agents.tools import visualization_tools
    from aqp.agents.tools.visualization_tools import SupersetDashboardTool
    from aqp.config import settings

    class _FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return None

        def list_dashboards(self):
            return []

        def list_datasets(self):
            return []

        def create_guest_token(self, *, resources):  # noqa: ARG002
            raise AssertionError("create_guest_token should not be called when uuid is missing")

    monkeypatch.setattr(settings, "superset_default_dashboard_uuid", "")
    monkeypatch.setattr(visualization_tools, "SupersetClient", _FakeClient, raising=False)

    raw = SupersetDashboardTool()._run(action="embed", dashboard_uuid=None)
    assert "error" in json.loads(raw)


def test_superset_dashboard_tool_lists_dashboards(monkeypatch) -> None:
    from aqp.agents.tools import visualization_tools
    from aqp.agents.tools.visualization_tools import SupersetDashboardTool

    class _FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return None

        def list_dashboards(self):
            return [{"id": 1, "dashboard_title": "A", "slug": "a"}]

        def list_datasets(self):
            return [{"id": 11, "table_name": "sp500", "schema": "aqp_equity"}]

    monkeypatch.setattr(visualization_tools, "SupersetClient", lambda: _FakeClient(), raising=False)

    raw = SupersetDashboardTool()._run(action="list")
    payload = json.loads(raw)

    assert payload["dashboards"][0]["title"] == "A"
    assert payload["datasets"][0]["table_name"] == "sp500"
