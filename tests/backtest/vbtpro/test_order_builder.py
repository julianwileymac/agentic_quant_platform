"""Order builder + IOrderModel tests — no vbt-pro required."""
from __future__ import annotations

import pandas as pd
import pytest

from aqp.backtest.vbtpro.order_builder import (
    OrderArrays,
    build_order_arrays,
    signals_to_orders,
)
from aqp.backtest.vbtpro.signal_builder import SignalArrays
from aqp.core.interfaces import IOrderModel
from aqp.core.types import Symbol


def _make_close() -> pd.DataFrame:
    return pd.DataFrame(
        100.0,
        index=pd.date_range("2024-01-01", periods=5),
        columns=["AAPL.NASDAQ", "MSFT.NASDAQ"],
    )


class _DummyOrderModel(IOrderModel):
    """Emits +1 long on AAPL on day 1; -1 short on MSFT on day 3."""

    def generate_orders(self, bars, universe, context):
        close = context["close"]
        size = pd.DataFrame(0.0, index=close.index, columns=close.columns)
        size.iloc[1, 0] = 1.0
        size.iloc[3, 1] = -1.0
        return OrderArrays(size=size, size_type="targetpercent")


def test_build_order_arrays_invokes_model() -> None:
    close = _make_close()
    bars = (
        close.stack()
        .rename("close")
        .reset_index()
        .rename(columns={"level_0": "timestamp", "level_1": "vt_symbol"})
    )
    arr = build_order_arrays(
        _DummyOrderModel(),
        bars=bars,
        universe=[Symbol.parse(c) for c in close.columns],
        close=close,
    )
    assert arr.size.iloc[1, 0] == 1.0
    assert arr.size.iloc[3, 1] == -1.0
    assert arr.size_type == "targetpercent"


def test_to_kwargs_drops_none_values() -> None:
    close = _make_close()
    arr = OrderArrays(size=pd.DataFrame(0.0, index=close.index, columns=close.columns))
    kwargs = arr.to_kwargs()
    assert "size" in kwargs
    assert "size_type" in kwargs
    # Optional fields not set => not surfaced.
    assert "price" not in kwargs
    assert "fees" not in kwargs


def test_signals_to_orders_equal_weight() -> None:
    close = _make_close()
    entries = pd.DataFrame(False, index=close.index, columns=close.columns)
    entries.iloc[1, :] = True
    exits = pd.DataFrame(False, index=close.index, columns=close.columns)
    arr = signals_to_orders(
        SignalArrays(entries=entries, exits=exits),
        sizer="equal_weight",
        size_type="targetpercent",
    )
    # When both symbols are long, equal-weight => 0.5 each.
    assert arr.size.iloc[1].sum() == pytest.approx(1.0)
    assert arr.size.iloc[1, 0] == pytest.approx(0.5)


def test_signals_to_orders_unit() -> None:
    close = _make_close()
    entries = pd.DataFrame(False, index=close.index, columns=close.columns)
    entries.iloc[1, 0] = True
    exits = pd.DataFrame(False, index=close.index, columns=close.columns)
    arr = signals_to_orders(SignalArrays(entries=entries, exits=exits), sizer="unit")
    assert arr.size.iloc[1, 0] == 1.0
