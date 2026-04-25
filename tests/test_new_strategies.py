"""Smoke tests for the expanded strategy zoo.

Each new strategy gets a tiny `generate_signals` invocation on synthetic
bars to make sure the implementation returns a well-typed list (possibly
empty) without raising. We don't assert anything about the signals
themselves — that's the domain of each strategy's own documentation tests.
"""
from __future__ import annotations

import pandas as pd
import pytest

from aqp.core.types import Symbol


def _run(alpha, bars: pd.DataFrame, symbols: list[str]):
    universe = [Symbol.parse(s) for s in symbols]
    return alpha.generate_signals(bars, universe, {"current_time": bars["timestamp"].max()})


@pytest.fixture
def single_sym_bars(synthetic_bars: pd.DataFrame) -> pd.DataFrame:
    return synthetic_bars[synthetic_bars["vt_symbol"] == "AAA.NASDAQ"].copy()


def test_awesome_oscillator(single_sym_bars: pd.DataFrame) -> None:
    from aqp.strategies.awesome_oscillator_alpha import AwesomeOscillatorAlpha

    out = _run(AwesomeOscillatorAlpha(), single_sym_bars, ["AAA.NASDAQ"])
    assert isinstance(out, list)


def test_heikin_ashi(single_sym_bars: pd.DataFrame) -> None:
    from aqp.strategies.heikin_ashi_alpha import HeikinAshiAlpha

    out = _run(HeikinAshiAlpha(), single_sym_bars, ["AAA.NASDAQ"])
    assert isinstance(out, list)


def test_dual_thrust(single_sym_bars: pd.DataFrame) -> None:
    from aqp.strategies.dual_thrust_alpha import DualThrustAlpha

    out = _run(DualThrustAlpha(), single_sym_bars, ["AAA.NASDAQ"])
    assert isinstance(out, list)


def test_parabolic_sar(single_sym_bars: pd.DataFrame) -> None:
    from aqp.strategies.parabolic_sar_alpha import ParabolicSARAlpha

    out = _run(ParabolicSARAlpha(), single_sym_bars, ["AAA.NASDAQ"])
    assert isinstance(out, list)


def test_london_breakout(single_sym_bars: pd.DataFrame) -> None:
    from aqp.strategies.london_breakout_alpha import LondonBreakoutAlpha

    out = _run(LondonBreakoutAlpha(), single_sym_bars, ["AAA.NASDAQ"])
    assert isinstance(out, list)


def test_bollinger_w(single_sym_bars: pd.DataFrame) -> None:
    from aqp.strategies.bollinger_w_alpha import BollingerWAlpha

    out = _run(BollingerWAlpha(), single_sym_bars, ["AAA.NASDAQ"])
    assert isinstance(out, list)


def test_shooting_star(single_sym_bars: pd.DataFrame) -> None:
    from aqp.strategies.shooting_star_alpha import ShootingStarAlpha

    out = _run(ShootingStarAlpha(), single_sym_bars, ["AAA.NASDAQ"])
    assert isinstance(out, list)


def test_rsi_pattern(single_sym_bars: pd.DataFrame) -> None:
    from aqp.strategies.rsi_pattern_alpha import RsiPatternAlpha

    out = _run(RsiPatternAlpha(), single_sym_bars, ["AAA.NASDAQ"])
    assert isinstance(out, list)


def test_sma_cross_reference(single_sym_bars: pd.DataFrame) -> None:
    from aqp.strategies.examples.sma_cross import SmaCross

    out = _run(SmaCross(fast=5, slow=20), single_sym_bars, ["AAA.NASDAQ"])
    assert isinstance(out, list)


def test_sma4_cross_reference(single_sym_bars: pd.DataFrame) -> None:
    from aqp.strategies.examples.sma4_cross import Sma4Cross

    out = _run(Sma4Cross(n1=10, n2=30, n_enter=5, n_exit=3), single_sym_bars, ["AAA.NASDAQ"])
    assert isinstance(out, list)


def test_trailing_atr_reference(single_sym_bars: pd.DataFrame) -> None:
    from aqp.strategies.examples.trailing_atr import TrailingATRAlpha

    out = _run(TrailingATRAlpha(fast=5, slow=20, atr_period=10), single_sym_bars, ["AAA.NASDAQ"])
    assert isinstance(out, list)


def test_base_algo_example(single_sym_bars: pd.DataFrame) -> None:
    from aqp.strategies.base_algo_example import BaseAlgoExample

    out = _run(BaseAlgoExample(), single_sym_bars, ["AAA.NASDAQ"])
    assert isinstance(out, list)


def test_strategy_tags_export() -> None:
    from aqp.strategies import list_strategy_tags

    tags = list_strategy_tags()
    # Every new ported strategy should expose tags.
    for name in [
        "AwesomeOscillatorAlpha",
        "HeikinAshiAlpha",
        "DualThrustAlpha",
        "ParabolicSARAlpha",
        "LondonBreakoutAlpha",
        "BollingerWAlpha",
        "ShootingStarAlpha",
        "RsiPatternAlpha",
        "OilMoneyRegressionAlpha",
    ]:
        assert name in tags, f"{name} missing STRATEGY_TAGS"
