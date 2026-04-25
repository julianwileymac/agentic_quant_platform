"""Risk-parity portfolio construction (inverse-volatility weights)."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from aqp.core.interfaces import IPortfolioConstructionModel
from aqp.core.registry import register
from aqp.core.types import Direction, PortfolioTarget, Signal


@register("RiskParityPortfolio")
class RiskParityPortfolio(IPortfolioConstructionModel):
    """Equal risk contribution — approximated by inverse-volatility weights."""

    def __init__(
        self,
        max_positions: int = 20,
        long_only: bool = True,
        lookback_bars: int = 252,
    ) -> None:
        self.max_positions = int(max_positions)
        self.long_only = bool(long_only)
        self.lookback_bars = int(lookback_bars)

    def construct(self, signals: list[Signal], context: dict[str, Any]) -> list[PortfolioTarget]:
        if not signals:
            return []
        chosen = sorted(signals, key=lambda s: s.strength * s.confidence, reverse=True)[
            : self.max_positions
        ]
        tickers = [s.symbol.vt_symbol for s in chosen]
        history: pd.DataFrame = context.get("history", pd.DataFrame())
        if history.empty:
            return _equal(chosen)
        pivot = (
            history[history["vt_symbol"].isin(set(tickers))]
            .pivot(index="timestamp", columns="vt_symbol", values="close")
            .sort_index()
            .tail(self.lookback_bars)
            .pct_change()
            .dropna(how="all")
        )
        if pivot.empty:
            return _equal(chosen)
        vols = pivot.std()
        inv = 1.0 / vols.replace(0, np.nan)
        inv = inv.dropna()
        if inv.empty:
            return _equal(chosen)
        weights = inv / inv.sum()
        sign = {s.symbol.vt_symbol: 1.0 if s.direction == Direction.LONG else -1.0 for s in chosen}
        targets: list[PortfolioTarget] = []
        for vt_symbol, w in weights.items():
            if vt_symbol not in sign:
                continue
            signed = float(w) * sign[vt_symbol]
            if abs(signed) < 1e-4:
                continue
            signal = next(s for s in chosen if s.symbol.vt_symbol == vt_symbol)
            targets.append(
                PortfolioTarget(
                    symbol=signal.symbol,
                    target_weight=signed,
                    rationale=f"risk-parity w={w:.3f}",
                    horizon_days=signal.horizon_days,
                )
            )
        return targets


def _equal(signals: list[Signal]) -> list[PortfolioTarget]:
    w = 1.0 / len(signals)
    return [
        PortfolioTarget(
            symbol=s.symbol,
            target_weight=w * (1.0 if s.direction == Direction.LONG else -1.0),
            rationale="risk-parity fallback",
            horizon_days=s.horizon_days,
        )
        for s in signals
    ]
