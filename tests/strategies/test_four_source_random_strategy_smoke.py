"""Deterministic-random strategy smoke from the four-source cache."""
from __future__ import annotations

import pandas as pd
import pytest

from aqp.core.types import Symbol
from tests.four_source_random import SELECTED_ASSETS, SEED, pick_assets


def test_strategy_selection_manifest_is_stable() -> None:
    assert pick_assets(SEED) == SELECTED_ASSETS
    assert SELECTED_ASSETS["strategy"] == "IndicatorVoteAlpha"


def test_selected_strategy_runs_signal_generation(synthetic_bars: pd.DataFrame) -> None:
    selected = SELECTED_ASSETS["strategy"]
    bars = synthetic_bars[synthetic_bars["timestamp"] <= pd.Timestamp("2023-06-30")].copy()
    universe = [Symbol.parse(s) for s in sorted(bars["vt_symbol"].unique())[:3]]
    now = pd.Timestamp("2023-06-30")

    if selected == "IndicatorVoteAlpha":
        from aqp.strategies.sae.alphas import IndicatorVoteAlpha

        alpha = IndicatorVoteAlpha(
            indicators=["SMA:20", "EMA:12", "RSI:14"],
            min_buy_count=1,
            min_sell_count=1,
        )
    elif selected == "DualThrustAlpha":
        from aqp.strategies.dual_thrust_alpha import DualThrustAlpha

        alpha = DualThrustAlpha(lookback=4, k1=0.5, k2=0.5, allow_short=True)
    elif selected == "SectorMomentumAlpha":
        from aqp.strategies.analyzingalpha.alphas import SectorMomentumAlpha

        alpha = SectorMomentumAlpha(lookback=21)
    elif selected == "MLStockSelectionAlpha":
        from aqp.strategies.ml_selection import MLStockSelectionAlpha

        alpha = MLStockSelectionAlpha(
            model_kind="ridge",
            forward_horizon_days=5,
            top_quantile=0.7,
            retrain_each_call=True,
        )
    else:
        pytest.skip(f"Unsupported selected strategy: {selected}")

    signals = alpha.generate_signals(bars, universe, {"current_time": now})
    assert isinstance(signals, list)
    allowed = {s.vt_symbol for s in universe}
    for signal in signals:
        assert signal.symbol.vt_symbol in allowed
        assert 0.0 <= float(signal.strength) <= 1.0
