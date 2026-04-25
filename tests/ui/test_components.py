"""Component-library unit tests.

These tests exercise the non-rendering behaviour of the shared components
where possible — parsing, schema expansion, hook-rule compliance — so we
can catch regressions without spinning up a Solara kernel.
"""
from __future__ import annotations

import warnings

import pytest


@pytest.fixture(autouse=True)
def _strict_hook_warnings() -> None:
    """Turn any hook-rule warning into a test failure for the whole module."""
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "error",
            message=r"Failed to validate hooks.*",
            category=UserWarning,
        )
        yield


def test_plotly_figurewidget_available() -> None:
    """Guard: Solara's ``FigurePlotly`` renders via Plotly's ``FigureWidget``,
    which imports ``anywidget`` lazily at first use. If that import fails,
    every chart-bearing page 500s. Pin this here so CI catches it offline.
    """
    from plotly.graph_objs._figurewidget import FigureWidget

    assert FigureWidget.__name__ == "FigureWidget"


def test_component_exports() -> None:
    from aqp.ui import components

    expected = {
        "AgentTrace",
        "Candlestick",
        "CardGrid",
        "ChatBubble",
        "DashEmbed",
        "EntityTable",
        "EquityCard",
        "FieldSpec",
        "FormBuilder",
        "Heatmap",
        "IndicatorOverlay",
        "LiveStreamer",
        "MetricTile",
        "ModelCatalog",
        "ParameterEditor",
        "SplitPane",
        "StatsGrid",
        "TabPanel",
        "TabSpec",
        "TaskStreamer",
        "TileTrend",
        "YamlEditor",
        "use_api",
        "use_api_action",
    }
    assert expected.issubset(set(components.__all__))


def test_model_catalog_defaults_are_copies() -> None:
    from aqp.ui.components.forms.parameter_editor import ModelCatalog

    catalog = ModelCatalog(
        label="Test",
        entries={
            "Foo": {"module_path": "pkg.foo", "kwargs": {"n": 5, "flag": True}}
        },
    )
    d1 = catalog.defaults("Foo")
    d2 = catalog.defaults("Foo")
    d1["n"] = 999
    assert d2["n"] == 5, "defaults() must return a fresh copy per call"
    assert catalog.module_path("Foo") == "pkg.foo"
    assert catalog.module_path("Bar") is None


def test_indicator_overlay_panel_mapping() -> None:
    from aqp.ui.components.charts.candlestick import IndicatorOverlay

    ov = IndicatorOverlay(column="sma_20", label="SMA 20", panel="price")
    assert ov.render_label() == "SMA 20"
    assert ov.tags() == ["price"]


def test_tile_trend_tone() -> None:
    from aqp.ui.components.data.metric_tile import TileTrend

    assert TileTrend(delta=1.0, better="up").tone() == "success"
    assert TileTrend(delta=-1.0, better="up").tone() == "error"
    assert TileTrend(delta=0.0).tone() == "neutral"
    assert TileTrend(delta=1.0, better="down").tone() == "error"


def test_api_result_value_is_unwrapped() -> None:
    """Regression guard: ``result.value or {}`` must not invoke
    ``bool(Reactive)`` (which would call ``len(Reactive)`` and crash).

    Every page uses the ``result.value or {}`` / ``result.value or []``
    pattern; if ``_ApiResult.value`` ever reverts to returning the
    underlying ``solara.Reactive`` object, this test will fail loudly
    before we ship it.
    """
    import solara

    from aqp.ui.components.data.use_api import _ApiResult

    handle = _ApiResult(
        refresh=lambda: None,
        reactive=solara.Reactive({"engaged": False, "reason": ""}),
        loading_reactive=solara.Reactive(False),
        error_reactive=solara.Reactive(""),
        last_updated_reactive=solara.Reactive(0.0),
    )

    # The exact idiom every page uses; must not raise.
    ks_dict = handle.value or {}
    assert isinstance(ks_dict, dict)
    assert ks_dict.get("engaged") is False

    # Same for a list-returning endpoint.
    list_handle = _ApiResult(
        refresh=lambda: None,
        reactive=solara.Reactive([]),
        loading_reactive=solara.Reactive(False),
        error_reactive=solara.Reactive(""),
        last_updated_reactive=solara.Reactive(0.0),
    )
    rows = list_handle.value or []
    assert rows == []

    # loading/error/last_updated are plain scalars (not Reactives).
    assert handle.loading is False
    assert handle.error == ""
    assert handle.last_updated == 0.0
    assert handle.ready is True
    # reactive is still reachable for widget bindings.
    assert isinstance(handle.reactive, solara.Reactive)
