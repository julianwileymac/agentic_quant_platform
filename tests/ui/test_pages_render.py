"""End-to-end render tests.

These tests actually mount each page via ``reacton.render`` with the
HTTP client patched to return canned JSON, so any render-time exception
(like ``len(Reactive)`` crashes from treating ``use_api().value`` as a
reactive) fails the test before it reaches a browser.

The Solara shell (ipyvuetify etc.) is initialised inside ``reacton`` —
we don't need a JS runtime, just a Python kernel.
"""
from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

import pytest
import reacton


FAKE_RESPONSES: dict[str, Any] = {
    "/portfolio/kill_switch": {"engaged": False, "reason": ""},
    "/portfolio/orders?limit=1": [],
    "/portfolio/orders?limit=100": [],
    "/portfolio/fills?limit=100": [],
    "/portfolio/ledger?limit=200": [],
    "/backtest/runs?limit=5": [],
    "/backtest/runs?limit=25": [],
    "/backtest/runs?limit=30": [],
    "/backtest/runs?limit=50": [],
    "/backtest/optimize?limit=20": [],
    "/paper/runs?limit=5": [],
    "/paper/runs?limit=30": [],
    "/brokers/": [
        {
            "name": "simulated",
            "available": True,
            "configured": True,
            "paper": True,
            "description": "Simulated venue",
            "missing_extras": [],
        },
    ],
    "/brokers/schema": {
        "methods": [
            {"name": "query_account", "readonly": True, "description": "Cash summary", "params": []},
        ]
    },
    "/health": {
        "status": "ok",
        "ollama": True,
        "redis": True,
        "postgres": True,
        "chromadb": True,
        "models": [],
    },
    "/data/describe": [],
    "/data/indicators": [
        {"name": "SMA", "category": "trend", "default_period": 20, "description": "SMA"},
    ],
    "/factors/operators": [
        {"name": "Mean", "category": "rolling", "arity": 2, "description": "Rolling mean."},
    ],
    "/strategies/": [],
    "/agents/crews?limit=40": [],
    "/live/subscriptions": [],
    "/ml/models?limit=100": [],
    "/ml/registered": {"tree": ["LGBModel"], "linear": [], "torch": [], "handlers": [], "datasets": []},
    "/ml/models?limit=50": [],
    "/ml/split-plans?limit=50": [],
    "/ml/pipelines?limit=50": [],
    "/ml/experiments?limit=50": [],
    "/ml/deployments?limit=100": [],
    "/data/catalog?limit=50": [],
}


def _fake_get(path: str, **_kwargs: Any) -> Any:
    """Mirror of :func:`aqp.ui.api_client.get`, but reads from the canned dict."""
    if path in FAKE_RESPONSES:
        return FAKE_RESPONSES[path]
    # Cheap heuristic: paths returning lists by convention start with /portfolio/
    # /backtest/runs, /paper/runs, /agents/crews etc.
    if any(part in path for part in ("runs", "crews", "orders", "fills", "ledger", "subscriptions", "operators", "models", "describe", "indicators", "venues", "brokers/")):
        return []
    return {}


def _fake_post(_path: str, **_kwargs: Any) -> Any:
    return {"task_id": "00000000", "stream_url": "/chat/stream/00000000"}


def _fake_put(_path: str, **_kwargs: Any) -> Any:
    return {}


def _fake_delete(_path: str, **_kwargs: Any) -> Any:
    return {"ok": True}


@pytest.fixture(autouse=True)
def _patch_api(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace every network-hitting helper with a canned response."""
    import aqp.ui.api_client as api_client

    monkeypatch.setattr(api_client, "get", _fake_get)
    monkeypatch.setattr(api_client, "post", _fake_post)
    monkeypatch.setattr(api_client, "put", _fake_put)
    monkeypatch.setattr(api_client, "delete", _fake_delete)

    # Re-export into the use_api module so its internal ``_get`` symbol
    # also returns canned data. We go through ``importlib`` because the
    # package ``__init__`` re-exports the ``use_api`` function under the
    # same name as the submodule, which shadows the module attribute.
    use_api_mod = importlib.import_module("aqp.ui.components.data.use_api")
    monkeypatch.setattr(use_api_mod, "_get", _fake_get)


PAGES_TO_RENDER = [
    "aqp.ui.pages.dashboard_home",
    "aqp.ui.pages.chat",
    "aqp.ui.pages.strategy",
    "aqp.ui.pages.portfolio",
    "aqp.ui.pages.live_market",
    "aqp.ui.pages.api_playground",
    "aqp.ui.pages.paper_runs",
    "aqp.ui.pages.factor_workbench",
    "aqp.ui.pages.indicator_builder",
    "aqp.ui.pages.crew_trace",
    "aqp.ui.pages.ml_model_detail",
    "aqp.ui.pages.optimizer",
    "aqp.ui.pages.monte_carlo",
    "aqp.ui.pages.data_browser",
]


@pytest.mark.parametrize("module_name", PAGES_TO_RENDER)
def test_page_renders_without_raising(module_name: str) -> None:
    """Mount ``<module>.Page()`` via reacton and assert no exception is raised.

    This catches regressions like ``bool(Reactive)``/``len(Reactive)`` that
    the static hook validator can't see.
    """
    module = importlib.import_module(module_name)
    component: Callable[[], None] | None = getattr(module, "Page", None)
    assert callable(component), f"{module_name}.Page missing"

    element = component()
    # ``handle_error=False`` makes reacton re-raise any render exception instead
    # of swallowing it into a `solara.Error` banner.
    widget, rc = reacton.render(element, handle_error=False)
    try:
        assert widget is not None
    finally:
        rc.close()
