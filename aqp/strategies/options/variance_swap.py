"""Synthetic variance swap via static option replication.

The variance swap pays out :math:`\\sigma^2_{\\text{realised}} -
\\sigma^2_{\\text{strike}}`. Carr-Madan (2001) shows it can be
replicated statically by a portfolio of OTM puts (below the forward)
and OTM calls (above the forward), each weighted by :math:`1/K^2`.

Concretely the replication is::

    V = 2/T * sum( w_i * (P_i + C_i) )

where :math:`w_i = \\Delta K_i / K_i^2`. This module emits the
opening trade signals on a periodic cadence — the order router is
responsible for actually finding the contracts.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol


@dataclass(frozen=True)
class StripLeg:
    strike: float
    weight: float
    is_call: bool


def replication_weights(
    forward: float,
    strikes: np.ndarray,
) -> list[StripLeg]:
    """Carr-Madan replication weights.

    Parameters
    ----------
    forward
        The forward price F at expiry (use spot when r=q=0).
    strikes
        Sorted 1-D array of available strikes.
    """
    strikes = np.asarray(strikes, dtype=float)
    strikes = np.sort(strikes)
    legs: list[StripLeg] = []
    # Trapezoidal Delta K spacing.
    dk = np.gradient(strikes)
    for k, delta in zip(strikes, dk):
        if k <= 0 or delta <= 0:
            continue
        w = float(delta / (k * k))
        is_call = k >= forward
        legs.append(StripLeg(strike=float(k), weight=w, is_call=bool(is_call)))
    return legs


@register(
    "VarianceSwapSynthetic",
    source="research_report_2026",
    category="volatility",
    kind="strategy",
)
class VarianceSwapSynthetic(IAlphaModel):
    """Static-replication variance swap.

    Parameters
    ----------
    underlying
        Vt symbol of the underlying.
    open_day_of_week
        ISO weekday on which a fresh strip is opened.
    n_strikes
        Number of strikes in the strip (centred on the forward).
    strike_width
        Spacing between adjacent strikes in dollars.
    side
        ``"long"`` to buy the strip (pay realised variance, receive
        strike), ``"short"`` to sell.
    """

    def __init__(
        self,
        underlying: str = "SPY.NYSE",
        open_day_of_week: int = 0,
        n_strikes: int = 11,
        strike_width: float = 5.0,
        side: str = "long",
    ) -> None:
        self.underlying = underlying
        self.open_day_of_week = int(open_day_of_week)
        self.n_strikes = int(n_strikes)
        self.strike_width = float(strike_width)
        if side not in {"long", "short"}:
            raise ValueError("side must be 'long' or 'short'")
        self.side = side

    def _build_strip(self, when: datetime, forward: float) -> list[Signal]:
        half = self.n_strikes // 2
        strikes = np.array(
            [forward + (i - half) * self.strike_width for i in range(self.n_strikes)],
            dtype=float,
        )
        legs = replication_weights(forward, strikes)
        sym = Symbol.parse(self.underlying)
        direction = Direction.LONG if self.side == "long" else Direction.SHORT
        out: list[Signal] = []
        for leg in legs:
            out.append(
                Signal(
                    symbol=sym,
                    strength=float(leg.weight),
                    direction=direction,
                    timestamp=when,
                    confidence=0.6,
                    horizon_days=30,
                    source="VarianceSwapSynthetic",
                    rationale=(
                        f"{self.side} {('call' if leg.is_call else 'put')} "
                        f"strike={leg.strike:.2f} w={leg.weight:.4f}"
                    ),
                )
            )
        return out

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
        if when.weekday() != self.open_day_of_week:
            return []
        spot = float(last["close"])
        return self._build_strip(when, spot)
