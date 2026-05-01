"""Vertical option spread P&L math.

Source: ``inspiration/stock-analysis-engine-master/analysis_engine/build_option_spread_details.py``
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VerticalSpread:
    width: float
    net_debit: float
    max_profit: float
    max_loss: float
    breakeven: float
    mid_value: float
    is_call: bool


def vertical_spread(
    long_strike: float,
    short_strike: float,
    long_premium: float,
    short_premium: float,
    is_call: bool = True,
) -> VerticalSpread:
    """Bull-call / bear-put vertical spread P&L.

    For a debit call spread (``is_call=True``, ``long_strike < short_strike``):

    - max_profit = (short_strike - long_strike) - net_debit
    - max_loss   = net_debit
    - breakeven  = long_strike + net_debit

    For a credit put spread (``is_call=False``, ``long_strike < short_strike``):

    - max_profit = net_credit
    - max_loss   = (short_strike - long_strike) - net_credit
    - breakeven  = short_strike - net_credit
    """
    width = abs(long_strike - short_strike)
    net = long_premium - short_premium  # positive = debit, negative = credit

    if is_call:
        max_profit = width - net
        max_loss = net
        breakeven = long_strike + net
    else:
        # For a put credit spread sold for net credit:
        max_profit = -net
        max_loss = width + net
        breakeven = short_strike + net

    mid = (max_profit - max_loss) / 2.0
    return VerticalSpread(
        width=float(width),
        net_debit=float(net),
        max_profit=float(max_profit),
        max_loss=float(max_loss),
        breakeven=float(breakeven),
        mid_value=float(mid),
        is_call=bool(is_call),
    )


def iron_condor(
    put_long_strike: float,
    put_short_strike: float,
    call_short_strike: float,
    call_long_strike: float,
    put_long_prem: float,
    put_short_prem: float,
    call_short_prem: float,
    call_long_prem: float,
) -> dict[str, float]:
    """Iron condor P&L from four legs.

    Returns max_profit, max_loss, lower_breakeven, upper_breakeven.
    """
    put_credit = put_short_prem - put_long_prem
    call_credit = call_short_prem - call_long_prem
    total_credit = put_credit + call_credit
    put_width = put_short_strike - put_long_strike
    call_width = call_long_strike - call_short_strike
    width = max(put_width, call_width)
    return {
        "max_profit": float(total_credit),
        "max_loss": float(width - total_credit),
        "lower_breakeven": float(put_short_strike - total_credit),
        "upper_breakeven": float(call_short_strike + total_credit),
        "credit": float(total_credit),
    }


__all__ = ["VerticalSpread", "iron_condor", "vertical_spread"]
