"""Structural bars (López de Prado, AFML ch. 2).

Replace fixed-duration OHLCV bars with *information-driven* bars:

- :func:`dollar_bars` — close a bar once cumulative traded notional exceeds a threshold.
- :func:`volume_bars` — close a bar once cumulative traded volume exceeds a threshold.
- :func:`tick_bars` — close a bar once a fixed number of trades have happened.
- :func:`imbalance_bars` — close on signed-volume imbalance (TIB / VIB / DIB).

Structural bars are more statistically stationary than wall-clock bars
and deliver markedly better IC for many supervised models.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


_REQUIRED_TRADE_COLS = ("price", "volume")


def _coerce(trades: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in _REQUIRED_TRADE_COLS if c not in trades.columns]
    if missing:
        raise ValueError(f"Trade frame missing required columns: {missing}")
    frame = trades.copy()
    if not isinstance(frame.index, pd.DatetimeIndex):
        if "timestamp" in frame.columns:
            frame["timestamp"] = pd.to_datetime(frame["timestamp"])
            frame = frame.set_index("timestamp").sort_index()
        else:
            raise ValueError("trades must be indexed by timestamp (or carry a ``timestamp`` column)")
    return frame


def _bars_from_events(
    trades: pd.DataFrame,
    event_indices: np.ndarray,
) -> pd.DataFrame:
    """Build OHLCV rows from a sorted array of end-of-bar row positions."""
    bars: list[dict[str, object]] = []
    start = 0
    for end in event_indices:
        end = int(end)
        sub = trades.iloc[start : end + 1]
        if sub.empty:
            start = end + 1
            continue
        bars.append(
            {
                "timestamp": sub.index[-1],
                "open": float(sub["price"].iloc[0]),
                "high": float(sub["price"].max()),
                "low": float(sub["price"].min()),
                "close": float(sub["price"].iloc[-1]),
                "volume": float(sub["volume"].sum()),
                "dollar": float((sub["price"] * sub["volume"]).sum()),
                "ticks": int(len(sub)),
            }
        )
        start = end + 1
    if not bars:
        return pd.DataFrame(
            columns=["timestamp", "open", "high", "low", "close", "volume", "dollar", "ticks"],
        )
    return pd.DataFrame(bars).set_index("timestamp")


def dollar_bars(trades: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """Close each bar once cumulative traded notional ≥ ``threshold``."""
    trades = _coerce(trades)
    dollars = (trades["price"] * trades["volume"]).cumsum().values
    if threshold <= 0:
        raise ValueError("threshold must be positive")
    buckets = np.floor(dollars / float(threshold)).astype(int)
    diffs = np.diff(buckets, prepend=buckets[0] - 1)
    events = np.where(diffs > 0)[0]
    # Each ``events[i]`` marks the *start* of a new bucket, so the *previous*
    # index is the end of the previous bar.
    ends = events - 1
    ends = ends[ends > 0]
    if len(ends) == 0 or ends[-1] != len(trades) - 1:
        ends = np.append(ends, len(trades) - 1)
    return _bars_from_events(trades, ends)


def volume_bars(trades: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """Close each bar once cumulative volume ≥ ``threshold``."""
    trades = _coerce(trades)
    if threshold <= 0:
        raise ValueError("threshold must be positive")
    cum = trades["volume"].cumsum().values
    buckets = np.floor(cum / float(threshold)).astype(int)
    diffs = np.diff(buckets, prepend=buckets[0] - 1)
    events = np.where(diffs > 0)[0]
    ends = events - 1
    ends = ends[ends > 0]
    if len(ends) == 0 or ends[-1] != len(trades) - 1:
        ends = np.append(ends, len(trades) - 1)
    return _bars_from_events(trades, ends)


def tick_bars(trades: pd.DataFrame, ticks_per_bar: int) -> pd.DataFrame:
    """Close each bar after a fixed number of trades."""
    trades = _coerce(trades)
    if ticks_per_bar <= 0:
        raise ValueError("ticks_per_bar must be positive")
    n = len(trades)
    ends = np.arange(ticks_per_bar - 1, n, ticks_per_bar)
    if len(ends) == 0 or ends[-1] != n - 1:
        ends = np.append(ends, n - 1)
    return _bars_from_events(trades, ends)


def imbalance_bars(
    trades: pd.DataFrame,
    initial_threshold: float = 1_000_000.0,
    ema_span: int = 100,
    price_col: str = "price",
) -> pd.DataFrame:
    """Dollar imbalance bars (DIB).

    Uses the sign of successive price changes as the trade direction
    proxy (``+1`` up-tick, ``-1`` down-tick) and closes each bar once
    the cumulative signed-dollar ``|θ|`` crosses an adaptive threshold.
    The threshold is EWMA-updated between bars.
    """
    trades = _coerce(trades)
    price = trades[price_col].values
    volume = trades["volume"].values
    if len(price) == 0:
        return pd.DataFrame()
    # Sign of price changes (zero → carry previous sign).
    dp = np.diff(price, prepend=price[0])
    side = np.sign(dp)
    for i in range(1, len(side)):
        if side[i] == 0:
            side[i] = side[i - 1] if side[i - 1] != 0 else 1
    if side[0] == 0:
        side[0] = 1
    signed_dollar = side * price * volume
    theta_cum = 0.0
    threshold = float(initial_threshold)
    ends: list[int] = []
    bar_dollars: list[float] = []
    last = 0
    alpha = 2.0 / (max(int(ema_span), 1) + 1.0)
    for i, val in enumerate(signed_dollar):
        theta_cum += val
        if abs(theta_cum) >= threshold:
            ends.append(i)
            bar_dollars.append(abs(theta_cum))
            theta_cum = 0.0
            last = i
            if bar_dollars:
                threshold = (1 - alpha) * threshold + alpha * bar_dollars[-1]
    if not ends or ends[-1] != len(signed_dollar) - 1:
        ends.append(len(signed_dollar) - 1)
    return _bars_from_events(trades, np.array(ends))


__all__ = [
    "dollar_bars",
    "imbalance_bars",
    "tick_bars",
    "volume_bars",
]
