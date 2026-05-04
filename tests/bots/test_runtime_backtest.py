"""TradingBot.backtest derivation + BotRuntime smoke (no DB / no engine)."""
from __future__ import annotations

from typing import Any

import pytest

from aqp.bots.base import BotMethodNotSupported
from aqp.bots.research_bot import ResearchBot
from aqp.bots.runtime import BotRuntime
from aqp.bots.spec import (
    BotAgentRef,
    BotSpec,
    DeploymentTargetSpec,
    MLDeploymentRef,
    UniverseRef,
)
from aqp.bots.trading_bot import TradingBot


def _trading_spec(**overrides: Any) -> BotSpec:
    base = dict(
        name="Smoke Trader",
        kind="trading",
        universe=UniverseRef(symbols=["AAPL.NASDAQ"]),
        strategy={
            "class": "FrameworkAlgorithm",
            "module_path": "aqp.strategies.framework",
            "kwargs": {"alpha_model": {"class": "DualMACrossoverAlpha"}},
        },
        backtest={"engine": "vbt-pro:signals", "kwargs": {"initial_cash": 10000.0}},
    )
    base.update(overrides)
    return BotSpec(**base)


def test_trading_bot_requires_strategy() -> None:
    with pytest.raises(ValueError):
        TradingBot(
            spec=BotSpec(
                name="No Strategy",
                kind="trading",
                strategy=None,
                backtest={"engine": "x"},
            )
        )


def test_trading_bot_requires_backtest() -> None:
    with pytest.raises(ValueError):
        TradingBot(
            spec=BotSpec(
                name="No BT",
                kind="trading",
                strategy={"class": "X"},
                backtest=None,
            )
        )


def test_derive_backtest_cfg_passes_strategy_and_backtest() -> None:
    bot = TradingBot(spec=_trading_spec())
    cfg = bot._derive_backtest_cfg(overrides={})
    assert "strategy" in cfg and "backtest" in cfg
    assert cfg["strategy"]["class"] == "FrameworkAlgorithm"
    assert cfg["backtest"]["engine"] == "vbt-pro:signals"
    assert cfg["backtest"]["kwargs"]["initial_cash"] == pytest.approx(10000.0)


def test_derive_backtest_cfg_injects_universe_when_missing() -> None:
    spec = _trading_spec(
        strategy={
            "class": "FrameworkAlgorithm",
            "module_path": "aqp.strategies.framework",
            # No universe_model in the strategy kwargs.
            "kwargs": {"alpha_model": {"class": "DualMACrossoverAlpha"}},
        },
        universe=UniverseRef(symbols=["MSFT.NASDAQ", "AAPL.NASDAQ"]),
    )
    bot = TradingBot(spec=spec)
    cfg = bot._derive_backtest_cfg(overrides={})
    uni = cfg["strategy"]["kwargs"]["universe_model"]
    assert uni["class"] == "StaticUniverse"
    assert uni["module_path"] == "aqp.strategies.universes"
    assert uni["kwargs"]["symbols"] == ["MSFT.NASDAQ", "AAPL.NASDAQ"]


def test_derive_backtest_cfg_injects_ml_deployment_id() -> None:
    spec = _trading_spec(
        ml_models=[MLDeploymentRef(deployment_id="dep-abc")],
        strategy={
            "class": "FrameworkAlgorithm",
            "module_path": "aqp.strategies.framework",
            "kwargs": {"alpha_model": {"class": "MLVbtAlpha", "kwargs": {}}},
        },
    )
    bot = TradingBot(spec=spec)
    cfg = bot._derive_backtest_cfg(overrides={})
    alpha_kwargs = cfg["strategy"]["kwargs"]["alpha_model"]["kwargs"]
    assert alpha_kwargs["deployment_id"] == "dep-abc"


def test_derive_backtest_cfg_does_not_overwrite_existing_deployment_id() -> None:
    spec = _trading_spec(
        ml_models=[MLDeploymentRef(deployment_id="dep-spec")],
        strategy={
            "class": "FrameworkAlgorithm",
            "kwargs": {"alpha_model": {"class": "MLVbtAlpha", "kwargs": {"deployment_id": "dep-explicit"}}},
        },
    )
    bot = TradingBot(spec=spec)
    cfg = bot._derive_backtest_cfg(overrides={})
    alpha_kwargs = cfg["strategy"]["kwargs"]["alpha_model"]["kwargs"]
    assert alpha_kwargs["deployment_id"] == "dep-explicit"


def test_derive_backtest_cfg_passes_through_data_source_override() -> None:
    bot = TradingBot(spec=_trading_spec())
    cfg = bot._derive_backtest_cfg(
        overrides={"data_source": {"kind": "iceberg_table", "iceberg_identifier": "ns.t"}}
    )
    assert cfg["data_source"]["kind"] == "iceberg_table"


def test_derive_paper_cfg_attaches_session_and_risk() -> None:
    spec = _trading_spec(
        deployment=DeploymentTargetSpec(target="paper_session", initial_cash=50000.0, dry_run=True),
    )
    bot = TradingBot(spec=spec)
    cfg = bot._derive_paper_cfg(overrides={})
    assert cfg["session"]["initial_cash"] == pytest.approx(50000.0)
    assert cfg["session"]["dry_run"] is True
    assert cfg["session"]["universe"] == ["AAPL.NASDAQ"]


def test_trading_bot_chat_raises() -> None:
    bot = TradingBot(spec=_trading_spec())
    with pytest.raises(BotMethodNotSupported):
        bot.chat("hi")


def test_research_bot_requires_agents() -> None:
    with pytest.raises(ValueError):
        ResearchBot(
            spec=BotSpec(
                name="Empty Research",
                kind="research",
                agents=[],
            )
        )


def test_research_bot_paper_disabled() -> None:
    bot = ResearchBot(
        spec=BotSpec(
            name="Reader",
            kind="research",
            agents=[BotAgentRef(spec_name="research.equity")],
        )
    )
    with pytest.raises(BotMethodNotSupported):
        bot.paper()


def test_research_bot_backtest_requires_strategy() -> None:
    bot = ResearchBot(
        spec=BotSpec(
            name="Reader",
            kind="research",
            agents=[BotAgentRef(spec_name="research.equity")],
        )
    )
    with pytest.raises(BotMethodNotSupported):
        bot.backtest()


def test_runtime_backtest_calls_run_backtest_from_config(monkeypatch) -> None:
    """Verify the runtime delegates to run_backtest_from_config without touching
    the actual backtest engine (we monkey-patch the entry point)."""
    captured: dict[str, Any] = {}

    def fake_run(cfg: dict[str, Any], run_name: str = "adhoc", **kw: Any) -> dict[str, Any]:
        captured["cfg"] = cfg
        captured["run_name"] = run_name
        return {"sharpe": 1.5, "total_return": 0.2, "engine": "vbt-pro:signals"}

    import aqp.backtest.runner as runner_mod

    monkeypatch.setattr(runner_mod, "run_backtest_from_config", fake_run)
    monkeypatch.setattr("aqp.bots.registry.persist_spec", lambda *a, **kw: None)

    bot = TradingBot(spec=_trading_spec())
    runtime = BotRuntime(bot, task_id=None)
    result = runtime.backtest(run_name="rt-test")
    assert result.status == "completed"
    assert result.target == "backtest"
    assert result.result["sharpe"] == pytest.approx(1.5)
    assert captured["run_name"] == "rt-test"
    assert captured["cfg"]["backtest"]["engine"] == "vbt-pro:signals"


def test_metrics_snapshot_evaluates_thresholds() -> None:
    spec = _trading_spec()
    spec = BotSpec.model_validate(
        {
            **spec.model_dump(mode="json"),
            "metrics": [
                {"name": "sharpe", "threshold": 1.0, "direction": "max"},
                {"name": "max_drawdown", "threshold": 0.2, "direction": "min"},
            ],
        }
    )
    bot = TradingBot(spec=spec)
    snap = bot.metrics_snapshot({"sharpe": 1.5, "max_drawdown": 0.1})
    assert snap["sharpe"]["passed"] is True
    assert snap["max_drawdown"]["passed"] is True
    fail_snap = bot.metrics_snapshot({"sharpe": 0.5, "max_drawdown": 0.3})
    assert fail_snap["sharpe"]["passed"] is False
    assert fail_snap["max_drawdown"]["passed"] is False
