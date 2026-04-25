"""Smoke tests: every Solara page module imports cleanly under hook validation.

These tests do not render the pages (that needs a live ipywidgets kernel)
— they simply verify that importing each page succeeds without the
``UserWarning: Failed to validate hooks`` that Solara raises when a
component violates the rules of hooks. A broken page would silently
regress to a non-functional state; these guards make the regression
loud.
"""
from __future__ import annotations

import importlib
import warnings

import pytest


PAGE_MODULES = [
    "aqp.ui.pages.dashboard_home",
    "aqp.ui.pages.chat",
    "aqp.ui.pages.strategy",
    "aqp.ui.pages.strategy_browser",
    "aqp.ui.pages.indicator_builder",
    "aqp.ui.pages.factor_workbench",
    "aqp.ui.pages.data",
    "aqp.ui.pages.data_browser",
    "aqp.ui.pages.live_market",
    "aqp.ui.pages.backtest",
    "aqp.ui.pages.optimizer",
    "aqp.ui.pages.monte_carlo",
    "aqp.ui.pages.ml_training",
    "aqp.ui.pages.ml_model_detail",
    "aqp.ui.pages.rl",
    "aqp.ui.pages.api_playground",
    "aqp.ui.pages.paper_runs",
    "aqp.ui.pages.portfolio",
    "aqp.ui.pages.dash_embed",
    "aqp.ui.pages.crew_trace",
    # Data-plane expansion pages.
    "aqp.ui.pages.sources",
    "aqp.ui.pages.credentials",
    "aqp.ui.pages.fred",
    "aqp.ui.pages.sec",
    "aqp.ui.pages.gdelt",
]


@pytest.mark.parametrize("module_name", PAGE_MODULES)
def test_page_imports_without_hook_warnings(module_name: str) -> None:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "error",
            message=r"Failed to validate hooks.*",
            category=UserWarning,
        )
        warnings.filterwarnings(
            "error",
            message=r".*found despite early return.*",
            category=UserWarning,
        )
        warnings.filterwarnings(
            "error",
            message=r".*found within a conditional.*",
            category=UserWarning,
        )
        mod = importlib.import_module(module_name)
    assert hasattr(mod, "Page"), f"{module_name} must expose a top-level `Page` component"


def test_app_route_map() -> None:
    from aqp.ui.app import Layout, Page, routes

    sections = {
        (route.data or {}).get("section")
        for route in routes
        if (route.data or {})
    }
    assert sections >= {"home", "research", "data", "lab", "execution", "monitor"}
    labels = {route.label for route in routes}
    assert "Dashboard" in labels
    assert "Indicator Builder" in labels
    assert "Factor Workbench" in labels
    assert "Crew Trace" in labels
    assert "Paper Runs" in labels
    assert "ML Models" in labels
    assert "Optimizer" in labels
    assert "Monte Carlo" in labels
    assert callable(Layout)
    assert callable(Page)
