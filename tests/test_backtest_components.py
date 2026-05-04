from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd

from aqp.backtest.components import AgentRuntimeAlpha, CompositeAlpha, ModelPredictionAlpha
from aqp.core.interfaces import IAlphaModel
from aqp.core.types import Direction, Signal, Symbol


class StaticAlpha(IAlphaModel):
    def __init__(self, direction: Direction) -> None:
        self.direction = direction

    def generate_signals(self, bars, universe, context):
        return [
            Signal(
                symbol=universe[0],
                strength=0.25,
                direction=self.direction,
                timestamp=context["current_time"],
                source="test",
            )
        ]


def test_composite_alpha_concatenates_signals(synthetic_bars: pd.DataFrame) -> None:
    alpha = CompositeAlpha([StaticAlpha(Direction.LONG), StaticAlpha(Direction.SHORT)])
    symbol = Symbol.parse("AAA.NASDAQ")
    signals = alpha.generate_signals(
        synthetic_bars[synthetic_bars["vt_symbol"] == symbol.vt_symbol],
        [symbol],
        {"current_time": datetime(2024, 1, 1)},
    )
    assert [signal.direction for signal in signals] == [Direction.LONG, Direction.SHORT]


class DummyModel:
    def predict(self, x):
        return np.array([0.3, -0.4])[: len(x)]


def test_model_prediction_alpha_emits_model_signals(synthetic_bars: pd.DataFrame) -> None:
    bars = synthetic_bars[synthetic_bars["vt_symbol"].isin(["AAA.NASDAQ", "BBB.NASDAQ"])].copy()
    bars["feature"] = np.arange(len(bars), dtype=float)
    alpha = ModelPredictionAlpha(
        model=DummyModel(),
        feature_columns=["feature"],
        long_threshold=0.1,
        short_threshold=-0.1,
    )
    signals = alpha.generate_signals(
        bars,
        [Symbol.parse("AAA.NASDAQ"), Symbol.parse("BBB.NASDAQ")],
        {"current_time": datetime(2024, 1, 1)},
    )
    assert {signal.direction for signal in signals} == {Direction.LONG, Direction.SHORT}


@dataclass
class DummyRun:
    output: dict


class DummyRuntime:
    def run(self, inputs):
        return DummyRun(
            {
                "action": "BUY",
                "size_pct": 0.4,
                "confidence": 0.9,
                "rationale": "unit test",
            }
        )


def test_agent_runtime_alpha_uses_runtime(monkeypatch, synthetic_bars: pd.DataFrame) -> None:
    import aqp.agents.runtime as runtime_mod

    monkeypatch.setattr(runtime_mod, "runtime_for", lambda spec_name: DummyRuntime())
    alpha = AgentRuntimeAlpha(spec_name="test.agent", max_symbols=1)
    symbol = Symbol.parse("AAA.NASDAQ")
    signals = alpha.generate_signals(
        synthetic_bars[synthetic_bars["vt_symbol"] == symbol.vt_symbol],
        [symbol],
        {"current_time": datetime(2024, 1, 1)},
    )
    assert len(signals) == 1
    assert signals[0].direction == Direction.LONG
    assert signals[0].strength == 0.4
