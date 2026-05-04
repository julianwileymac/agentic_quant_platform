"""Build wide-format order arrays for ``Portfolio.from_orders``.

The order path is the natural fit for agent-driven strategies where the
agent emits not just direction but precise sizes and (optionally) limit
prices. AQP's :class:`IOrderModel` produces an ``OrderArrays`` payload —
wide-format DataFrames indexed by timestamp with vt_symbol columns — that
this module reshapes into the kwargs ``Portfolio.from_orders`` accepts.

Two shapes are supported:

- **Direct** — caller passes an :class:`IOrderModel` instance; we call
  ``generate_orders`` once with the full ``bars`` panel.
- **From signals** — convenience wrapper that converts an existing
  :class:`SignalArrays` into orders by applying a sizer (uniform / equal
  weight / custom callable).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd

from aqp.backtest.vbtpro.signal_builder import SignalArrays
from aqp.core.interfaces import IOrderModel
from aqp.core.types import Symbol

logger = logging.getLogger(__name__)


@dataclass
class OrderArrays:
    """Wide-format order arrays consumed by ``Portfolio.from_orders``.

    All frames share the same index (timestamps) and columns (vt_symbols).
    """

    size: pd.DataFrame
    price: pd.DataFrame | None = None
    size_type: str = "amount"
    direction: pd.DataFrame | str | None = None
    fees: pd.DataFrame | float | None = None
    fixed_fees: pd.DataFrame | float | None = None
    slippage: pd.DataFrame | float | None = None

    extras: dict[str, Any] = field(default_factory=dict)

    def to_kwargs(self) -> dict[str, Any]:
        """Return the kwargs vbt-pro's ``Portfolio.from_orders`` accepts."""
        out: dict[str, Any] = {
            "size": self.size,
            "size_type": self.size_type,
        }
        if self.price is not None:
            out["price"] = self.price
        if self.direction is not None:
            out["direction"] = self.direction
        if self.fees is not None:
            out["fees"] = self.fees
        if self.fixed_fees is not None:
            out["fixed_fees"] = self.fixed_fees
        if self.slippage is not None:
            out["slippage"] = self.slippage
        out.update(self.extras)
        return out


def build_order_arrays(
    order_model: IOrderModel,
    bars: pd.DataFrame,
    universe: list[Symbol],
    close: pd.DataFrame,
    *,
    context: dict[str, Any] | None = None,
) -> OrderArrays:
    """Invoke an :class:`IOrderModel` and reshape its output for vbt-pro.

    The order model is expected to return either an :class:`OrderArrays`
    instance directly (preferred) or any object duck-compatible with the
    fields of :class:`OrderArrays`.
    """
    ctx = dict(context or {})
    ctx.setdefault("close", close)
    raw = order_model.generate_orders(bars, universe, ctx)
    if isinstance(raw, OrderArrays):
        return _reindex(raw, close)
    return _coerce(raw, close)


def signals_to_orders(
    signals: SignalArrays,
    *,
    sizer: Callable[[pd.DataFrame], pd.DataFrame] | str = "equal_weight",
    size_type: str = "targetpercent",
) -> OrderArrays:
    """Convert :class:`SignalArrays` to :class:`OrderArrays` via a sizer.

    This is the cheapest way to get from "I have entries/exits arrays" to
    the orders engine. Built-in sizers:

    - ``"equal_weight"`` — equal target weight across active long positions
      at each bar (1 / N where N is the number of longs); shorts use the
      same |weight| but negated.
    - ``"unit"`` — fixed +1 / -1 target shares regardless of count.

    Custom sizers receive the boolean **net** signal frame (long_entry +
    long_held - short_entry - short_held) and must return a same-shape
    frame of signed target sizes.
    """
    long_held = _state_from_entries(signals.entries, signals.exits)
    short_held = (
        _state_from_entries(signals.short_entries, signals.short_exits)
        if signals.short_entries is not None and signals.short_exits is not None
        else pd.DataFrame(False, index=signals.entries.index, columns=signals.entries.columns)
    )
    net = long_held.astype(int) - short_held.astype(int)

    if callable(sizer):
        size = sizer(net)
    elif sizer == "equal_weight":
        active = net.abs().sum(axis=1).astype(float).replace(0.0, float("nan"))
        weight = (1.0 / active).fillna(0.0)
        size = net.mul(weight, axis=0).fillna(0.0)
    elif sizer == "unit":
        size = net.astype(float)
    else:
        raise ValueError(f"Unknown sizer: {sizer!r}")

    return OrderArrays(size=size, size_type=size_type)


def _state_from_entries(entries: pd.DataFrame, exits: pd.DataFrame) -> pd.DataFrame:
    """Reconstruct a boolean held-position frame from entry/exit boolean arrays."""
    diff = entries.astype(int) - exits.astype(int)
    state = diff.cumsum().clip(lower=0, upper=1)
    return state.astype(bool)


def _reindex(arr: OrderArrays, close: pd.DataFrame) -> OrderArrays:
    def _re(df: pd.DataFrame | None) -> pd.DataFrame | None:
        if df is None:
            return None
        return df.reindex(index=close.index, columns=close.columns)

    return OrderArrays(
        size=_re(arr.size).fillna(0.0),  # type: ignore[union-attr]
        price=_re(arr.price) if isinstance(arr.price, pd.DataFrame) else arr.price,
        size_type=arr.size_type,
        direction=_re(arr.direction)
        if isinstance(arr.direction, pd.DataFrame)
        else arr.direction,
        fees=_re(arr.fees) if isinstance(arr.fees, pd.DataFrame) else arr.fees,
        fixed_fees=_re(arr.fixed_fees) if isinstance(arr.fixed_fees, pd.DataFrame) else arr.fixed_fees,
        slippage=_re(arr.slippage)
        if isinstance(arr.slippage, pd.DataFrame)
        else arr.slippage,
        extras=dict(arr.extras),
    )


def _coerce(raw: Any, close: pd.DataFrame) -> OrderArrays:
    size = getattr(raw, "size", None)
    if size is None:
        raise ValueError("OrderModel must return an object with a `size` DataFrame.")
    if not isinstance(size, pd.DataFrame):
        size = pd.DataFrame(size, index=close.index, columns=close.columns)
    arr = OrderArrays(
        size=size.reindex(index=close.index, columns=close.columns).fillna(0.0),
        price=getattr(raw, "price", None),
        size_type=str(getattr(raw, "size_type", "amount")),
        direction=getattr(raw, "direction", None),
        fees=getattr(raw, "fees", None),
        fixed_fees=getattr(raw, "fixed_fees", None),
        slippage=getattr(raw, "slippage", None),
        extras=dict(getattr(raw, "extras", {}) or {}),
    )
    return arr


__all__ = ["OrderArrays", "build_order_arrays", "signals_to_orders"]
