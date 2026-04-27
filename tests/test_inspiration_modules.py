"""Tests for the inspiration-extracted modules.

- :class:`aqp.strategies.universes.QuarterlyRotationUniverse`
- :mod:`aqp.strategies.regime_detection`
- :func:`aqp.utils.keys.register_keys_from_json`
- :func:`aqp.agents.prompts.forecaster.build_forecaster_prompt`
"""
from __future__ import annotations

import json

import pandas as pd

from aqp.agents.prompts.forecaster import (
    ForecasterContext,
    build_forecaster_prompt,
    map_bin_label,
)
from aqp.strategies.regime_detection import fast_overlay, slow_regime
from aqp.strategies.universes import QuarterlyRotationUniverse
from aqp.utils.keys import register_keys_from_json


def test_quarterly_rotation_builds_daily_universe():
    df = pd.DataFrame(
        {
            "trade_date": [
                "2024-01-01",
                "2024-01-01",
                "2024-04-01",
                "2024-04-01",
            ],
            "tic_name": ["AAA", "BBB", "AAA", "BBB"],
        }
    )
    calendar = pd.bdate_range("2024-01-01", "2024-06-30")
    uni = QuarterlyRotationUniverse(
        selection_df=df,
        trading_calendar=calendar,
        backtest_start="2024-01-01",
        backtest_end="2024-06-30",
    )

    feb = uni.select(pd.Timestamp("2024-02-15"), context={})
    assert {s.ticker for s in feb} == {"AAA", "BBB"}


def test_quarterly_rotation_empty_input():
    uni = QuarterlyRotationUniverse()
    assert uni.select(pd.Timestamp("2024-01-01"), context={}) == []


def test_slow_regime_detects_risk_off():
    # Long stable history then a recent crash + VIX spike — three signals fire.
    idx = pd.bdate_range("2023-01-01", "2024-12-31")
    n = len(idx)
    crash_start = n - 30
    spx_values = [100.0 + i * 0.05 for i in range(crash_start)]
    spx_values += [spx_values[-1] * 0.85] * (n - crash_start)
    vix_values = [15.0] * crash_start + [40.0] * (n - crash_start)
    spx = pd.Series(spx_values, index=idx)
    vix = pd.Series(vix_values, index=idx)
    report = slow_regime(spx, vix)
    assert report.state == "risk_off", report
    assert report.risk_score >= 2
    assert report.spx_below_ma_26w
    assert report.drawdown_stress


def test_slow_regime_detects_risk_on():
    idx = pd.bdate_range("2023-01-01", "2024-12-31")
    spx = pd.Series(range(len(idx)), index=idx).astype(float) + 100.0
    vix = pd.Series([12.0] * len(idx), index=idx).astype(float)
    report = slow_regime(spx, vix)
    assert report.state == "risk_on"


def test_fast_overlay_triggers_on_price_shock():
    idx = pd.bdate_range("2024-01-01", periods=10)
    spx = pd.Series([100.0] * 9 + [95.0], index=idx)
    vix = pd.Series([15.0] * 10, index=idx)
    report = fast_overlay(spx, vix, price_shock_pct=0.025)
    assert report.active is True
    assert report.price_shock is True


def test_register_keys_from_json(tmp_path, monkeypatch):
    target = tmp_path / "keys.json"
    target.write_text(
        json.dumps({"my_test_key": "abc123", "ANOTHER_KEY": "xyz"}),
        encoding="utf-8",
    )
    monkeypatch.delenv("MY_TEST_KEY", raising=False)
    monkeypatch.delenv("ANOTHER_KEY", raising=False)
    written = register_keys_from_json(target)
    assert "MY_TEST_KEY" in written
    assert "ANOTHER_KEY" in written
    import os

    assert os.environ["MY_TEST_KEY"] == "abc123"


def test_register_keys_does_not_override_unless_asked(tmp_path, monkeypatch):
    target = tmp_path / "keys.json"
    target.write_text(json.dumps({"keep_me": "new"}), encoding="utf-8")
    monkeypatch.setenv("KEEP_ME", "old")
    written = register_keys_from_json(target, override=False)
    assert "KEEP_ME" not in written
    import os

    assert os.environ["KEEP_ME"] == "old"


def test_map_bin_label():
    assert map_bin_label("U2") == "up by 1-2%"
    assert map_bin_label("D5+") == "down by more than 5%"


def test_build_forecaster_prompt_includes_components():
    ctx = ForecasterContext(
        company_intro="Acme Corp is a leading widget producer.",
        news_headlines=["Widget demand strong", "New product launch"],
        market_sentiment="Sentiment: bullish.",
        basic_financials="Revenue up 15% YoY.",
    )
    prompt = build_forecaster_prompt(
        symbol="ACME",
        start_date="2024-01-01",
        end_date="2024-01-08",
        prediction="up by 1-2%",
        context=ctx,
    )
    assert "Acme Corp" in prompt
    assert "Widget demand strong" in prompt
    assert "Revenue up 15%" in prompt
    assert "ACME" in prompt
    assert "up by 1-2%" in prompt
