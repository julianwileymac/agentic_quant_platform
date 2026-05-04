"""Deterministic random asset selection for four-source smoke tests."""
from __future__ import annotations

import random

SEED = 20260503

STRATEGY_CANDIDATES = [
    "DualThrustAlpha",
    "IndicatorVoteAlpha",
    "SectorMomentumAlpha",
    "MLStockSelectionAlpha",
]
MODEL_CANDIDATES = [
    "KerasMLPRegressor",
]
PIPELINE_CANDIDATES = [
    "finviz_screener",
    "finrl_fundamentals_panel_sample",
    "quant_trading_oil_money_sample",
]


def pick_assets(seed: int = SEED) -> dict[str, str]:
    rng = random.Random(seed)
    return {
        "strategy": rng.choice(STRATEGY_CANDIDATES),
        "model": rng.choice(MODEL_CANDIDATES),
        "pipeline": rng.choice(PIPELINE_CANDIDATES),
    }


SELECTED_ASSETS = pick_assets(SEED)

__all__ = ["MODEL_CANDIDATES", "PIPELINE_CANDIDATES", "SEED", "SELECTED_ASSETS", "STRATEGY_CANDIDATES", "pick_assets"]
