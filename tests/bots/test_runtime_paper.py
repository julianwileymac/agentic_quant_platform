"""Paper-session derivation + PaperSessionTarget smoke (no real session)."""
from __future__ import annotations

from typing import Any

import pytest

from aqp.bots.deploy import (
    BacktestOnlyTarget,
    BotDeploymentResult,
    DeploymentDispatcher,
    PaperSessionTarget,
)
from aqp.bots.spec import (
    BotSpec,
    DeploymentTargetSpec,
    UniverseRef,
)
from aqp.bots.trading_bot import TradingBot


def _trading_spec(**overrides: Any) -> BotSpec:
    base = dict(
        name="Paper Trader",
        kind="trading",
        universe=UniverseRef(symbols=["AAPL.NASDAQ"]),
        strategy={
            "class": "FrameworkAlgorithm",
            "module_path": "aqp.strategies.framework",
            "kwargs": {
                "alpha_model": {"class": "DualMACrossoverAlpha", "kwargs": {"fast": 5, "slow": 20}},
            },
        },
        backtest={"engine": "vbt-pro:signals", "kwargs": {"initial_cash": 10000.0}},
        deployment=DeploymentTargetSpec(
            target="paper_session",
            initial_cash=25000.0,
            heartbeat_seconds=15,
            dry_run=True,
        ),
    )
    base.update(overrides)
    return BotSpec(**base)


def test_paper_cfg_session_block_pulls_from_deployment_spec() -> None:
    bot = TradingBot(spec=_trading_spec())
    cfg = bot._derive_paper_cfg(overrides={})
    session = cfg["session"]
    assert session["initial_cash"] == pytest.approx(25000.0)
    assert session["heartbeat_seconds"] == 15
    assert session["dry_run"] is True
    assert session["universe"] == ["AAPL.NASDAQ"]


def test_paper_cfg_includes_risk_when_set() -> None:
    spec = _trading_spec()
    spec = BotSpec.model_validate(
        {**spec.model_dump(mode="json"), "risk": {"max_position_pct": 0.15, "max_daily_loss_pct": 0.01}}
    )
    bot = TradingBot(spec=spec)
    cfg = bot._derive_paper_cfg(overrides={})
    assert cfg["risk"]["max_position_pct"] == pytest.approx(0.15)
    assert cfg["risk"]["max_daily_loss_pct"] == pytest.approx(0.01)


def test_paper_cfg_explicit_brokerage_string_resolves_to_class_alias() -> None:
    spec = _trading_spec(deployment=DeploymentTargetSpec(target="paper_session", brokerage="alpaca"))
    bot = TradingBot(spec=spec)
    cfg = bot._derive_paper_cfg(overrides={})
    assert cfg["brokerage"] == {"class": "AlpacaBrokerage"}


def test_paper_cfg_simulated_brokerage_omits_block() -> None:
    spec = _trading_spec(deployment=DeploymentTargetSpec(target="paper_session", brokerage="simulated"))
    bot = TradingBot(spec=spec)
    cfg = bot._derive_paper_cfg(overrides={})
    # Simulated => no brokerage block (build_session_from_config defaults to SimulatedBrokerage).
    assert "brokerage" not in cfg


def test_paper_cfg_dict_brokerage_passes_through() -> None:
    spec = _trading_spec(
        deployment=DeploymentTargetSpec(
            target="paper_session",
            brokerage={"class": "AlpacaBrokerage", "kwargs": {"paper": True}},
        ),
    )
    bot = TradingBot(spec=spec)
    cfg = bot._derive_paper_cfg(overrides={})
    assert cfg["brokerage"]["kwargs"]["paper"] is True


def test_paper_cfg_overrides_replace_session_keys() -> None:
    bot = TradingBot(spec=_trading_spec())
    cfg = bot._derive_paper_cfg(overrides={"session": {"max_bars": 5}})
    assert cfg["session"]["max_bars"] == 5
    # untouched defaults remain
    assert cfg["session"]["dry_run"] is True


def test_dispatcher_routes_to_paper_session_target() -> None:
    dispatcher = DeploymentDispatcher()
    assert isinstance(dispatcher._targets["paper_session"], PaperSessionTarget)
    assert isinstance(dispatcher._targets["backtest_only"], BacktestOnlyTarget)


def test_dispatcher_unknown_target_raises() -> None:
    dispatcher = DeploymentDispatcher()
    bot = TradingBot(spec=_trading_spec())
    with pytest.raises(ValueError):
        dispatcher.deploy(bot, target="not-a-target")


def test_dispatcher_paper_invokes_target_deploy(monkeypatch) -> None:
    """Verify the dispatcher delegates without spinning up a real session."""
    import aqp.bots.deploy as deploy_mod

    captured: dict[str, Any] = {}

    def fake_deploy(self, bot, *, overrides):  # noqa: ARG001
        captured["target"] = self.name
        captured["bot_slug"] = bot.spec.slug
        captured["overrides"] = overrides
        return BotDeploymentResult(
            deployment_id="fake-dep-id",
            target=self.name,
            status="completed",
            started_at=0.0,
            bot_id=bot.bot_id,
            bot_slug=bot.spec.slug,
            duration_ms=0.0,
            result={"orders_submitted": 1, "fills": 0, "final_equity": 25001.0},
        )

    monkeypatch.setattr(deploy_mod.PaperSessionTarget, "deploy", fake_deploy)

    dispatcher = DeploymentDispatcher()
    bot = TradingBot(spec=_trading_spec())
    result = dispatcher.deploy(bot, target="paper_session", overrides={"foo": "bar"})

    assert result.status == "completed"
    assert captured["target"] == "paper_session"
    assert captured["bot_slug"] == "paper-trader"
    assert captured["overrides"] == {"foo": "bar"}


def test_runtime_paper_calls_session_run(monkeypatch) -> None:
    """Verify BotRuntime.paper() builds a session and awaits its run()."""
    from aqp.bots.runtime import BotRuntime

    class FakeSession:
        def __init__(self) -> None:
            self.task_id = None
            self.runs = 0

        async def run(self):  # noqa: ANN201
            self.runs += 1
            from dataclasses import dataclass

            @dataclass
            class _Result:
                run_id: str
                status: str
                bars_seen: int
                final_equity: float

            return _Result(run_id="paper-fake", status="completed", bars_seen=10, final_equity=25001.0)

    bot = TradingBot(spec=_trading_spec())
    fake = FakeSession()
    monkeypatch.setattr(bot, "paper", lambda **kw: fake)
    monkeypatch.setattr("aqp.bots.registry.persist_spec", lambda *a, **kw: None)

    runtime = BotRuntime(bot, task_id=None)
    result = runtime.paper(run_name="rt-paper")
    assert result.status == "completed"
    assert result.target == "paper_session"
    assert fake.runs == 1
    assert result.result["bars_seen"] == 10
