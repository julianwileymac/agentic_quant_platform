"""Volatility-risk-premium short straddle with delta hedging.

The variance risk premium (VRP) is the persistent gap between option-
implied volatility and realised volatility. The simplest harvest is
a short straddle: sell a call and put at the same ATM strike,
collecting the time-decay premium. The dangerous side is the
unhedged directional exposure; the standard fix is continuous
delta-hedging — buy/sell the underlying so total portfolio delta
stays near zero.

This module is a *registered traded strategy* (vs. just the P&L math
helpers in :mod:`aqp.options.spreads`). It emits two kinds of signals:

1. **Open** signals on scheduled rebalance dates (e.g. weekly DTE).
2. **Hedge** signals on every bar: a buy / sell of the underlying
   sized to neutralise the aggregate portfolio delta computed from the
   current option mids and the underlying price.

Hedging assumes the AQP order router can carry the position and that
``context['portfolio']`` exposes the current option holdings (a list
of `{strike, dte, put_or_call, qty, delta}` rows). When no portfolio
context is supplied the strategy falls back to emitting the open
trade only — useful in unit tests and for first-day deployment.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol


@dataclass(frozen=True)
class OptionLeg:
    """Description of a single option leg in the portfolio."""

    strike: float
    dte_days: int
    is_call: bool
    quantity: float
    delta: float


def _bs_atm_delta(is_call: bool) -> float:
    """For perfectly ATM options, delta ≈ ±0.5 (call: +0.5, put: -0.5)."""
    return 0.5 if is_call else -0.5


@register(
    "VRPDeltaHedgedStraddle",
    source="research_report_2026",
    category="volatility",
    kind="strategy",
)
class VRPDeltaHedgedStraddle(IAlphaModel):
    """Short ATM straddle, delta-hedged.

    Parameters
    ----------
    underlying
        Vt symbol of the underlying instrument (e.g. ``SPY.NYSE``).
    open_day_of_week
        ISO weekday (0 = Monday) on which a fresh straddle is opened.
    dte_days
        Days-to-expiry of each fresh straddle.
    contracts
        Number of contracts per side (call + put quantity each).
    delta_tolerance
        Absolute portfolio delta beyond which a hedge signal fires.
    """

    def __init__(
        self,
        underlying: str = "SPY.NYSE",
        open_day_of_week: int = 0,
        dte_days: int = 7,
        contracts: int = 1,
        delta_tolerance: float = 0.1,
    ) -> None:
        self.underlying = underlying
        self.open_day_of_week = int(open_day_of_week)
        self.dte_days = int(dte_days)
        self.contracts = int(contracts)
        self.delta_tolerance = float(delta_tolerance)

    def _open_straddle(
        self, when: datetime, atm_strike: float
    ) -> list[Signal]:
        symbol = Symbol.parse(self.underlying)
        legs: list[Signal] = []
        for is_call in (True, False):
            legs.append(
                Signal(
                    symbol=symbol,
                    strength=float(self.contracts),
                    direction=Direction.SHORT,
                    timestamp=when,
                    confidence=0.7,
                    horizon_days=self.dte_days,
                    source="VRPDeltaHedgedStraddle",
                    rationale=(
                        f"open short {'call' if is_call else 'put'} "
                        f"strike={atm_strike:.2f} dte={self.dte_days}d"
                    ),
                )
            )
        return legs

    def _portfolio_delta(self, portfolio: list[OptionLeg]) -> float:
        return float(sum(leg.delta * leg.quantity for leg in portfolio))

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        if bars.empty:
            return []
        # Only operate on the underlying.
        proxy = bars[bars["vt_symbol"] == self.underlying].sort_values("timestamp")
        if proxy.empty:
            return []
        last = proxy.iloc[-1]
        when = pd.Timestamp(last["timestamp"]).to_pydatetime()
        atm_strike = float(last["close"])
        signals: list[Signal] = []
        if when.weekday() == self.open_day_of_week:
            signals.extend(self._open_straddle(when, atm_strike))

        # Hedge step: compute aggregate delta from context["portfolio"].
        portfolio_raw = context.get("portfolio") if isinstance(context, dict) else None
        if portfolio_raw is None:
            return signals
        portfolio: list[OptionLeg] = []
        for leg in portfolio_raw:
            if isinstance(leg, OptionLeg):
                portfolio.append(leg)
            elif isinstance(leg, dict):
                portfolio.append(
                    OptionLeg(
                        strike=float(leg.get("strike", atm_strike)),
                        dte_days=int(leg.get("dte_days", self.dte_days)),
                        is_call=bool(leg.get("is_call", True)),
                        quantity=float(leg.get("quantity", 0.0)),
                        delta=float(
                            leg.get(
                                "delta",
                                _bs_atm_delta(bool(leg.get("is_call", True))),
                            )
                        ),
                    )
                )
        if not portfolio:
            return signals
        net_delta = self._portfolio_delta(portfolio)
        if abs(net_delta) <= self.delta_tolerance:
            return signals
        # Hedge: trade the underlying opposite to the delta sign.
        hedge_direction = Direction.SHORT if net_delta > 0 else Direction.LONG
        signals.append(
            Signal(
                symbol=Symbol.parse(self.underlying),
                strength=float(abs(net_delta)),
                direction=hedge_direction,
                timestamp=when,
                confidence=0.9,
                horizon_days=1,
                source="VRPDeltaHedgedStraddle",
                rationale=(
                    f"delta hedge: net_delta={net_delta:.3f} > "
                    f"tolerance={self.delta_tolerance:.3f}"
                ),
            )
        )
        return signals


_ = math  # keep math import for future Greek refinements
