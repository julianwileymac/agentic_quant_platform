"""Cross-sectional residual mean reversion (Fama-French-style).

Regress each stock's return on a small set of macroeconomic risk
factors (market / size / value, or whichever columns the bars
provide), then trade the residual.

For each stock:

.. math::

    r_i = \\alpha_i + \\beta_{i,m} R_m + \\beta_{i,s} \\mathrm{SMB}
        + \\beta_{i,v} \\mathrm{HML} + \\epsilon_i.

The strategy signal is :math:`-\\epsilon_i` normalised across the
universe so the portfolio is dollar-neutral.
"""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np
import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol


def _ols_residual(y: np.ndarray, X: np.ndarray) -> float:
    """Return the latest residual from an OLS fit of y on X.

    Falls back to ``y[-1] - y.mean()`` when X is rank-deficient.
    """
    if y.size < 2 or X.size == 0:
        return float(y[-1] - y.mean()) if y.size else 0.0
    try:
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        pred = X @ beta
        residual = float(y[-1] - pred[-1])
        return residual
    except np.linalg.LinAlgError:
        return float(y[-1] - y.mean())


@register(
    "CrossSectionalResidualAlpha",
    source="research_report_2026",
    category="statistical_arbitrage",
    kind="strategy",
)
class CrossSectionalResidualAlpha(IAlphaModel):
    """Factor-neutralised residual mean reversion.

    Parameters
    ----------
    lookback
        Bars used to compute returns + factor regression.
    factor_columns
        Bar columns to use as the risk-factor matrix. Each must be a
        time series of factor values matching the bar timestamps.
    z_threshold
        Minimum absolute residual z-score to emit a signal.
    hold_bars
        Forecast horizon attached to each Signal.
    """

    def __init__(
        self,
        lookback: int = 60,
        factor_columns: Sequence[str] = ("mkt_excess", "smb", "hml"),
        z_threshold: float = 0.5,
        hold_bars: int = 5,
    ) -> None:
        self.lookback = int(lookback)
        self.factor_columns = tuple(factor_columns)
        self.z_threshold = float(z_threshold)
        self.hold_bars = int(hold_bars)

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        if bars.empty:
            return []
        universe_set = {s.vt_symbol for s in universe}
        rows: list[dict[str, Any]] = []
        now = context.get("current_time")
        available_factors = [c for c in self.factor_columns if c in bars.columns]
        for vt_symbol, sub in bars.groupby("vt_symbol", sort=False):
            if vt_symbol not in universe_set:
                continue
            sub = sub.sort_values("timestamp").tail(self.lookback)
            if len(sub) < max(10, len(available_factors) + 2):
                continue
            close = sub["close"].astype(float).to_numpy()
            ret = np.diff(np.log(np.maximum(close, 1e-12)))
            if ret.size < len(available_factors) + 2:
                continue
            if available_factors:
                X = (
                    sub[available_factors]
                    .astype(float)
                    .iloc[-ret.size :]
                    .to_numpy()
                )
                # Add a constant column for the alpha intercept.
                X = np.hstack([np.ones((X.shape[0], 1)), X])
            else:
                # No factors — fall back to a cross-sectional mean
                # neutralisation (residual = ret[-1] - mean(ret)).
                X = np.ones((ret.size, 1))
            residual = _ols_residual(ret, X)
            rows.append(
                {
                    "vt_symbol": vt_symbol,
                    "residual": float(residual),
                    "ts": sub["timestamp"].iloc[-1],
                }
            )
        if not rows:
            return []
        df = pd.DataFrame(rows)
        sigma = float(df["residual"].std() or 1.0)
        if sigma <= 1e-12:
            return []
        df["z"] = df["residual"] / sigma
        df["weight"] = -df["residual"]
        gross = float(df["weight"].abs().sum())
        if gross < 1e-12:
            return []
        df["weight"] = df["weight"] / gross
        signals: list[Signal] = []
        for row in df.itertuples():
            if abs(row.z) < self.z_threshold:
                continue
            direction = Direction.LONG if row.weight > 0 else Direction.SHORT
            signals.append(
                Signal(
                    symbol=Symbol.parse(row.vt_symbol),
                    strength=float(min(abs(row.weight), 1.0)),
                    direction=direction,
                    timestamp=now or row.ts,
                    confidence=float(min(abs(row.z) / max(self.z_threshold, 1e-6), 1.0)),
                    horizon_days=self.hold_bars,
                    source="CrossSectionalResidualAlpha",
                    rationale=(
                        f"residual={row.residual:.5f} z={row.z:.2f} "
                        f"factors={list(self.factor_columns)}"
                    ),
                )
            )
        return signals
