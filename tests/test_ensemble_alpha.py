"""Tests for :class:`aqp.strategies.ml_alphas.EnsembleAlpha`."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.types import Direction, Signal, Symbol
from aqp.strategies.ml_alphas import EnsembleAlpha


class _StubAlpha(IAlphaModel):
    def __init__(self, score_map: dict[str, float]) -> None:
        self.score_map = score_map

    def generate_signals(self, bars: pd.DataFrame, universe: list[Symbol], context: dict[str, Any]):
        out = []
        for sym, score in self.score_map.items():
            if abs(score) < 1e-6:
                continue
            out.append(
                Signal(
                    symbol=Symbol.parse(sym),
                    strength=abs(score),
                    direction=Direction.LONG if score > 0 else Direction.SHORT,
                    timestamp=datetime(2024, 1, 1),
                    confidence=0.9,
                    source="stub",
                    rationale="",
                )
            )
        return out


def test_ensemble_sums_scores_across_alphas():
    a1 = _StubAlpha({"AAA.NASDAQ": 0.6})
    a2 = _StubAlpha({"AAA.NASDAQ": 0.5, "BBB.NASDAQ": -0.7})
    ensemble = EnsembleAlpha(
        alphas=[a1, a2],
        long_threshold=0.05,
        short_threshold=-0.05,
    )
    universe = [Symbol.parse("AAA.NASDAQ"), Symbol.parse("BBB.NASDAQ")]
    sigs = ensemble.generate_signals(
        bars=pd.DataFrame({"timestamp": [pd.Timestamp("2024-01-01")]}),
        universe=universe,
        context={},
    )
    by_sym = {s.symbol.vt_symbol: s for s in sigs}
    assert "AAA.NASDAQ" in by_sym
    assert by_sym["AAA.NASDAQ"].direction == Direction.LONG
    assert by_sym["BBB.NASDAQ"].direction == Direction.SHORT


def test_ensemble_respects_thresholds():
    a1 = _StubAlpha({"AAA.NASDAQ": 0.02})
    ensemble = EnsembleAlpha(
        alphas=[a1],
        long_threshold=0.05,
        short_threshold=-0.05,
    )
    sigs = ensemble.generate_signals(
        bars=pd.DataFrame({"timestamp": [pd.Timestamp("2024-01-01")]}),
        universe=[Symbol.parse("AAA.NASDAQ")],
        context={},
    )
    assert sigs == []


def test_ensemble_weighting():
    a1 = _StubAlpha({"AAA.NASDAQ": 0.4})
    a2 = _StubAlpha({"AAA.NASDAQ": -0.4})
    # With equal weights they cancel out; weight a1 heavier and net long.
    ensemble = EnsembleAlpha(alphas=[a1, a2], weights=[2.0, 1.0])
    sigs = ensemble.generate_signals(
        bars=pd.DataFrame({"timestamp": [pd.Timestamp("2024-01-01")]}),
        universe=[Symbol.parse("AAA.NASDAQ")],
        context={},
    )
    assert len(sigs) == 1
    assert sigs[0].direction == Direction.LONG
