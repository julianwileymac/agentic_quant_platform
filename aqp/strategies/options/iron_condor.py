"""Iron condor as a *traded* options strategy.

Wraps the static P&L helpers in :mod:`aqp.options.spreads` into a
:class:`IAlphaModel` that opens a fresh four-leg condor on a
scheduled cadence and emits unwind signals when the underlying
breaches one of the short strikes.

Strike placement
================

Strikes are placed by IV multiplier instead of absolute width so the
strategy auto-scales to volatility regime:

- ``short_iv_mult`` controls how far OTM the short strikes sit
  (multiples of one-sigma move).
- ``wing_width`` is the dollar width between short and long strikes
  on each side.
"""
from __future__ import annotations

from datetime import datetime
import math
from typing import Any

import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol


@register(
    "IronCondorAlpha",
    source="research_report_2026",
    category="volatility",
    kind="strategy",
)
class IronCondorAlpha(IAlphaModel):
    """Short iron condor on a single underlying.

    Parameters
    ----------
    underlying
        Vt symbol of the underlying (e.g. ``SPY.NYSE``).
    open_day_of_week
        ISO weekday on which fresh condors open.
    dte_days
        DTE of the condor at open.
    short_iv_mult
        Distance from the spot to the short strikes, in multiples of
        one-sigma move (sigma derived from the recent realised vol).
    wing_width
        Dollar width between short and long strikes on each wing.
    vol_lookback
        Bars to use for the realised-vol estimate.
    breach_buffer
        Fractional buffer past the short strike at which the strategy
        emits an emergency unwind signal.
    """

    def __init__(
        self,
        underlying: str = "SPY.NYSE",
        open_day_of_week: int = 0,
        dte_days: int = 30,
        short_iv_mult: float = 1.0,
        wing_width: float = 5.0,
        vol_lookback: int = 20,
        breach_buffer: float = 0.05,
    ) -> None:
        self.underlying = underlying
        self.open_day_of_week = int(open_day_of_week)
        self.dte_days = int(dte_days)
        self.short_iv_mult = float(short_iv_mult)
        self.wing_width = float(wing_width)
        self.vol_lookback = int(vol_lookback)
        self.breach_buffer = float(breach_buffer)

    def _vol_estimate(self, sub: pd.DataFrame) -> float:
        if len(sub) < self.vol_lookback + 1:
            return 0.0
        close = sub["close"].astype(float).to_numpy()
        # Use simple sigma of log returns.
        log_returns = pd.Series(close).pct_change().dropna()
        return float(log_returns.tail(self.vol_lookback).std() * math.sqrt(252.0))

    def _legs(
        self, when: datetime, spot: float, sigma: float
    ) -> list[Signal]:
        # ATM-relative strikes; sigma * spot * sqrt(dte/252) is the
        # expected one-sigma move over the holding period.
        one_sigma = max(sigma, 1e-3) * spot * math.sqrt(self.dte_days / 252.0)
        short_put = spot - self.short_iv_mult * one_sigma
        long_put = short_put - self.wing_width
        short_call = spot + self.short_iv_mult * one_sigma
        long_call = short_call + self.wing_width

        sym = Symbol.parse(self.underlying)
        legs: list[Signal] = []
        for strike, is_call, direction, tag in (
            (long_put, False, Direction.LONG, "long_put"),
            (short_put, False, Direction.SHORT, "short_put"),
            (short_call, True, Direction.SHORT, "short_call"),
            (long_call, True, Direction.LONG, "long_call"),
        ):
            legs.append(
                Signal(
                    symbol=sym,
                    strength=1.0,
                    direction=direction,
                    timestamp=when,
                    confidence=0.7,
                    horizon_days=self.dte_days,
                    source="IronCondorAlpha",
                    rationale=(
                        f"{tag} strike={strike:.2f} kind={'C' if is_call else 'P'} "
                        f"sigma={sigma:.3f} one_sigma={one_sigma:.2f}"
                    ),
                )
            )
        return legs

    def _check_unwind(
        self, when: datetime, spot: float, sigma: float
    ) -> list[Signal]:
        # If the spot is well past the short strike, signal unwind.
        one_sigma = max(sigma, 1e-3) * spot * math.sqrt(self.dte_days / 252.0)
        short_put = spot - self.short_iv_mult * one_sigma
        short_call = spot + self.short_iv_mult * one_sigma
        if spot <= short_put * (1.0 - self.breach_buffer) or spot >= short_call * (
            1.0 + self.breach_buffer
        ):
            return [
                Signal(
                    symbol=Symbol.parse(self.underlying),
                    strength=1.0,
                    direction=Direction.SHORT,  # close all short legs first
                    timestamp=when,
                    confidence=0.95,
                    horizon_days=1,
                    source="IronCondorAlpha",
                    rationale="emergency unwind: spot breached short strike buffer",
                )
            ]
        return []

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        if bars.empty:
            return []
        sub = bars[bars["vt_symbol"] == self.underlying].sort_values("timestamp")
        if sub.empty:
            return []
        last = sub.iloc[-1]
        when = pd.Timestamp(last["timestamp"]).to_pydatetime()
        spot = float(last["close"])
        sigma = self._vol_estimate(sub)

        signals: list[Signal] = []
        if when.weekday() == self.open_day_of_week:
            signals.extend(self._legs(when, spot, sigma))
        # Unwind check fires every bar.
        signals.extend(self._check_unwind(when, spot, sigma))
        return signals
