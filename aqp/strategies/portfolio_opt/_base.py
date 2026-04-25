"""Shared helpers for ``portfolio_opt`` optimizers.

Every concrete optimizer needs to:

1. Slice the top-``N`` signals (``_top_signals``).
2. Pivot a history frame into returns (``_returns_from_history``).
3. Convert a weight dict into :class:`PortfolioTarget` objects
   (``_targets_from_weights``).

Factoring this into a mixin keeps each optimizer focused on the
optimisation core instead of repeating the plumbing.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from aqp.core.types import Direction, PortfolioTarget, Signal

logger = logging.getLogger(__name__)


def _top_signals(signals: list[Signal], max_positions: int) -> list[Signal]:
    return sorted(signals, key=lambda s: s.strength * s.confidence, reverse=True)[
        : max_positions
    ]


def _returns_from_history(
    history: pd.DataFrame,
    tickers: list[str],
    lookback_bars: int,
) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame()
    try:
        pivot = (
            history[history["vt_symbol"].isin(set(tickers))]
            .pivot(index="timestamp", columns="vt_symbol", values="close")
            .sort_index()
            .tail(lookback_bars)
        )
    except Exception:
        logger.exception("history pivot failed")
        return pd.DataFrame()
    return pivot.pct_change().dropna(how="all")


def _prices_from_history(
    history: pd.DataFrame,
    tickers: list[str],
    lookback_bars: int,
) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame()
    try:
        return (
            history[history["vt_symbol"].isin(set(tickers))]
            .pivot(index="timestamp", columns="vt_symbol", values="close")
            .sort_index()
            .tail(lookback_bars)
            .dropna(how="all")
        )
    except Exception:
        logger.exception("price pivot failed")
        return pd.DataFrame()


def _targets_from_weights(
    weights: dict[str, float],
    signals: list[Signal],
    rationale_prefix: str,
) -> list[PortfolioTarget]:
    sign = {s.symbol.vt_symbol: 1.0 if s.direction == Direction.LONG else -1.0 for s in signals}
    lookup = {s.symbol.vt_symbol: s for s in signals}
    targets: list[PortfolioTarget] = []
    for vt, w in weights.items():
        if vt not in sign:
            continue
        signed = float(w) * sign[vt]
        if abs(signed) < 1e-4:
            continue
        sig = lookup[vt]
        targets.append(
            PortfolioTarget(
                symbol=sig.symbol,
                target_weight=float(signed),
                rationale=f"{rationale_prefix} w={w:.3f}",
                horizon_days=sig.horizon_days,
            )
        )
    return targets


def _equal_weights(signals: list[Signal], rationale: str) -> list[PortfolioTarget]:
    if not signals:
        return []
    w = 1.0 / len(signals)
    return [
        PortfolioTarget(
            symbol=s.symbol,
            target_weight=w * (1.0 if s.direction == Direction.LONG else -1.0),
            rationale=rationale,
            horizon_days=s.horizon_days,
        )
        for s in signals
    ]


def _inverse_vol_weights(returns: pd.DataFrame) -> dict[str, float]:
    vols = returns.std().replace(0.0, np.nan)
    inv = 1.0 / vols.dropna()
    if inv.empty:
        return {}
    return (inv / inv.sum()).to_dict()


__all__ = [
    "_equal_weights",
    "_inverse_vol_weights",
    "_prices_from_history",
    "_returns_from_history",
    "_targets_from_weights",
    "_top_signals",
]
