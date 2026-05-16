"""Residual momentum (Blitz, Huij, Martens 2011).

Computes momentum on idiosyncratic returns after regressing out the
market / size / value factors. The residual-momentum effect is
empirically much more stable than raw-price momentum because it
strips out systematic risk-on / risk-off swings.
"""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np
import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol


@register(
    "ResidualMomentumAlpha",
    source="research_report_2026",
    category="momentum",
    kind="strategy",
)
class ResidualMomentumAlpha(IAlphaModel):
    """Top-decile / bottom-decile residual-momentum portfolio.

    Parameters
    ----------
    lookback
        Bars to use for the factor regression.
    formation_period
        Window over which residual returns are accumulated to produce
        the momentum signal.
    factor_columns
        Bar columns supplying the factor time series.
    top_quantile / bottom_quantile
        Quantile cuts for the long / short legs.
    hold_bars
        Forecast horizon attached to each Signal.
    """

    def __init__(
        self,
        lookback: int = 252,
        formation_period: int = 126,
        factor_columns: Sequence[str] = ("mkt_excess", "smb", "hml"),
        top_quantile: float = 0.1,
        bottom_quantile: float = 0.1,
        hold_bars: int = 21,
    ) -> None:
        self.lookback = int(lookback)
        self.formation_period = int(formation_period)
        self.factor_columns = tuple(factor_columns)
        self.top_quantile = float(top_quantile)
        self.bottom_quantile = float(bottom_quantile)
        self.hold_bars = int(hold_bars)

    def _residual_returns(self, sub: pd.DataFrame) -> np.ndarray | None:
        """Run the factor regression and return the residual return series."""
        if len(sub) < self.lookback:
            return None
        close = sub["close"].astype(float).to_numpy()
        ret = np.diff(np.log(np.maximum(close, 1e-12)))
        available = [c for c in self.factor_columns if c in sub.columns]
        if not available:
            return ret  # no factors → use raw returns
        X = sub[available].astype(float).iloc[-ret.size :].to_numpy()
        X = np.hstack([np.ones((X.shape[0], 1)), X])
        try:
            beta, *_ = np.linalg.lstsq(X, ret, rcond=None)
            residual = ret - X @ beta
            return residual
        except np.linalg.LinAlgError:
            return ret

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: Sequence[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        if bars.empty:
            return []
        universe_set = {s.vt_symbol for s in universe}
        rows: list[dict[str, Any]] = []
        now = context.get("current_time")
        for vt_symbol, sub in bars.groupby("vt_symbol", sort=False):
            if vt_symbol not in universe_set:
                continue
            sub = sub.sort_values("timestamp").tail(self.lookback)
            residual = self._residual_returns(sub)
            if residual is None or residual.size < self.formation_period:
                continue
            signal = float(np.sum(residual[-self.formation_period :]))
            rows.append(
                {
                    "vt_symbol": vt_symbol,
                    "signal": signal,
                    "ts": sub["timestamp"].iloc[-1],
                }
            )
        if not rows:
            return []
        df = pd.DataFrame(rows).sort_values("signal", ascending=False)
        n_top = max(1, int(round(len(df) * self.top_quantile)))
        n_bot = max(1, int(round(len(df) * self.bottom_quantile)))
        longs = df.head(n_top)
        shorts = df.tail(n_bot)

        signals: list[Signal] = []
        per_long = 1.0 / float(max(n_top, 1))
        per_short = 1.0 / float(max(n_bot, 1))
        for row in longs.itertuples():
            signals.append(
                Signal(
                    symbol=Symbol.parse(row.vt_symbol),
                    strength=float(per_long),
                    direction=Direction.LONG,
                    timestamp=now or row.ts,
                    confidence=float(min(max(row.signal, 0.0) * 5.0, 1.0)),
                    horizon_days=self.hold_bars,
                    source="ResidualMomentumAlpha",
                    rationale=f"residual momentum sum={row.signal:.4f}",
                )
            )
        for row in shorts.itertuples():
            signals.append(
                Signal(
                    symbol=Symbol.parse(row.vt_symbol),
                    strength=float(per_short),
                    direction=Direction.SHORT,
                    timestamp=now or row.ts,
                    confidence=float(min(abs(min(row.signal, 0.0)) * 5.0, 1.0)),
                    horizon_days=self.hold_bars,
                    source="ResidualMomentumAlpha",
                    rationale=f"residual momentum sum={row.signal:.4f}",
                )
            )
        return signals
