"""Spread / basket builders for stat-arb research.

Source: ``inspiration/notebooks-master/commodity_{crush,crack}_spread_stat_arb.ipynb``
plus standard calendar-spread arithmetic.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SpreadDefinition:
    """Linear combination of legs ``sum(weight_i * leg_i)``.

    ``legs`` maps ``vt_symbol`` → weight. Positive weight = long.
    """

    name: str
    legs: dict[str, float]
    description: str = ""


def soybean_crush() -> SpreadDefinition:
    """Soybean crush spread: 1 bean = 11 oil + 4.4 meal (per CME spec).

    Default vt_symbols use ICE/CME continuous contract conventions. Adjust
    the symbol strings to your data before using.
    """
    return SpreadDefinition(
        name="soybean_crush",
        legs={
            "ZS=F.CME": -1.0,   # short 1 soybean
            "ZL=F.CME": 11.0,   # long 11 soy oil
            "ZM=F.CME": 4.4,    # long 4.4 soy meal
        },
        description="Crush spread = 11*Oil + 4.4*Meal - Bean",
    )


def petroleum_crack_321() -> SpreadDefinition:
    """3-2-1 petroleum crack: 3 crude → 2 gasoline + 1 heating oil."""
    return SpreadDefinition(
        name="crack_321",
        legs={
            "CL=F.NYM": -3.0,
            "RB=F.NYM": 2.0,
            "HO=F.NYM": 1.0,
        },
        description="3-2-1 crack = 2*Gasoline + 1*HeatingOil - 3*Crude",
    )


def calendar_spread(front_symbol: str, back_symbol: str) -> SpreadDefinition:
    """Plain calendar spread (front - back)."""
    return SpreadDefinition(
        name=f"cal_{front_symbol}_{back_symbol}",
        legs={front_symbol: 1.0, back_symbol: -1.0},
        description="Calendar spread = front - back",
    )


def evaluate_spread(spread: SpreadDefinition, prices: pd.DataFrame) -> pd.Series:
    """Compute the spread time series.

    ``prices`` is a wide DataFrame indexed by timestamp with one column
    per ``vt_symbol``. Missing legs raise ``KeyError``.
    """
    missing = [sym for sym in spread.legs if sym not in prices.columns]
    if missing:
        raise KeyError(f"Spread {spread.name} missing legs: {missing}")
    parts = [prices[sym] * w for sym, w in spread.legs.items()]
    out = pd.concat(parts, axis=1).sum(axis=1)
    return out.rename(spread.name)


def spread_zscore(spread_series: pd.Series, window: int = 60) -> pd.Series:
    """Rolling z-score of a spread (used for entry/exit thresholds)."""
    rolling = spread_series.rolling(window, min_periods=window // 2)
    return (spread_series - rolling.mean()) / rolling.std().replace(0.0, float("nan"))


__all__ = [
    "SpreadDefinition",
    "calendar_spread",
    "evaluate_spread",
    "petroleum_crack_321",
    "soybean_crush",
    "spread_zscore",
]
