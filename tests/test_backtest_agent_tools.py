from __future__ import annotations

from datetime import datetime

from aqp.agents.trading.types import AgentDecision, TraderAction
from aqp.agents.tools import TOOL_REGISTRY
from aqp.agents.tools.backtest_tool import BacktestTool, _apply_engine_override
from aqp.strategies.agentic.decision_provider import (
    CachedAgentDecisionProvider,
    coerce_timestamp,
)


def test_backtest_tools_are_registered() -> None:
    assert "backtest_compare" in TOOL_REGISTRY
    assert "vectorbt_sweep" in TOOL_REGISTRY


def test_apply_engine_override_builds_fallback_config() -> None:
    cfg = {"strategy": {"kwargs": {}}, "backtest": {"kwargs": {"initial_cash": 100}}}
    out = _apply_engine_override(
        cfg,
        engine="vectorbt-pro",
        fallback_engines=["vectorbt", "event"],
    )
    assert out["backtest"]["engine"] == "fallback"
    assert out["backtest"]["primary"] == "vectorbt-pro"
    assert out["backtest"]["fallbacks"] == ["vectorbt", "event"]


def test_backtest_tool_defaults_to_vectorbt_pro(monkeypatch) -> None:
    import aqp.backtest.runner as runner

    seen = {}

    def fake_run(cfg, run_name="adhoc"):
        seen["engine"] = cfg["backtest"]["engine"]
        return {"run_name": run_name, "engine": seen["engine"]}

    monkeypatch.setattr(runner, "run_backtest_from_config", fake_run)
    output = BacktestTool()._run(
        """
strategy:
  class: Dummy
  kwargs: {}
backtest:
  kwargs: {}
""",
        name="tool-default",
    )
    assert seen["engine"] == "vectorbt-pro"
    assert "vectorbt-pro" in output


def test_cached_agent_decision_provider_sync_bridge(tmp_path) -> None:
    provider = CachedAgentDecisionProvider(strategy_id="provider-test", cache_root=str(tmp_path))
    ts = datetime(2024, 1, 2)
    provider.cache.put(
        AgentDecision(
            vt_symbol="AAA.NASDAQ",
            timestamp=ts,
            action=TraderAction.BUY,
            size_pct=0.2,
            confidence=0.8,
        )
    )
    decision = provider.decide_sync("AAA.NASDAQ", ts)
    assert decision is not None
    assert decision.action == TraderAction.BUY


def test_coerce_timestamp_accepts_iso_string() -> None:
    assert coerce_timestamp("2024-01-02").year == 2024
