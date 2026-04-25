"""Smoke tests for FastAPI schemas and app wiring."""
from __future__ import annotations

import pytest

from aqp.api.schemas import BacktestRequest, ChatRequest


def test_schemas_round_trip() -> None:
    req = ChatRequest(prompt="hello", tier="quick")
    assert req.tier == "quick"


def test_backtest_request_accepts_nested_config() -> None:
    cfg = {"strategy": {"class": "FrameworkAlgorithm"}, "backtest": {"class": "EventDrivenBacktester"}}
    req = BacktestRequest(config=cfg, run_name="demo")
    assert req.config["strategy"]["class"] == "FrameworkAlgorithm"


def test_app_lists_routes() -> None:
    fastapi = pytest.importorskip("fastapi")  # noqa: F841
    from aqp.api.main import app

    paths = [r.path for r in app.routes if hasattr(r, "path")]
    assert "/health" in paths
    assert "/chat" in paths
    assert "/agents/crew/run" in paths
    assert "/backtest/run" in paths
    assert "/rl/train" in paths
    assert "/data/ingest" in paths
    assert "/portfolio/orders" in paths
