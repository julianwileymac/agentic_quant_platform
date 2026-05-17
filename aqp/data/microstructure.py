"""Order-book microstructure features.

Pure pandas / numpy implementations so they slot into both the bar-based
:mod:`aqp.backtest` engine and the future LOB engine described in
``extractions/_FUTURE_PROMPTS/lob_adapter_prompt.md``.

Function signatures accept either scalars or array-likes (``pd.Series`` /
``np.ndarray``) and return the same shape. NaNs are emitted where inputs
are missing.

Sources:
- ``inspiration/hftbacktest-master/examples/Market Making with Alpha - Order Book Imbalance.ipynb``
- ``inspiration/hftbacktest-master/examples/Working with Market Depth and Trades.ipynb``
- ``inspiration/hftbacktest-master/py-hftbacktest/hftbacktest/binding.py`` event schema.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


_EPS = 1e-12


def _as_array(x: Any) -> np.ndarray:
    if isinstance(x, pd.Series):
        return x.to_numpy(dtype=float, copy=False)
    return np.asarray(x, dtype=float)


def order_book_imbalance(bid_qty: Any, ask_qty: Any) -> Any:
    """Order-book imbalance ``(Q_bid - Q_ask) / (Q_bid + Q_ask)``.

    Output range is ``[-1, +1]`` (positive = bid-side pressure).
    Preserves :class:`pd.Series` index when both inputs are Series.
    """
    if isinstance(bid_qty, pd.Series) and isinstance(ask_qty, pd.Series):
        denom = bid_qty + ask_qty
        return (bid_qty - ask_qty) / denom.where(denom != 0, _EPS)
    bid = _as_array(bid_qty)
    ask = _as_array(ask_qty)
    return (bid - ask) / (bid + ask + _EPS)


def microprice(
    bid_price: Any,
    ask_price: Any,
    bid_qty: Any,
    ask_qty: Any,
) -> Any:
    """Microprice ``(P_ask * Q_bid + P_bid * Q_ask) / (Q_bid + Q_ask)``.

    Volume-weighted refinement of the mid-price; converges to the side
    with deeper queue.
    """
    if isinstance(bid_price, pd.Series):
        denom = bid_qty + ask_qty
        return (ask_price * bid_qty + bid_price * ask_qty) / denom.where(denom != 0, _EPS)
    bp, ap = _as_array(bid_price), _as_array(ask_price)
    bq, aq = _as_array(bid_qty), _as_array(ask_qty)
    return (ap * bq + bp * aq) / (bq + aq + _EPS)


def weighted_spread(
    bid_prices: np.ndarray,
    ask_prices: np.ndarray,
    bid_qtys: np.ndarray,
    ask_qtys: np.ndarray,
    depth_levels: int = 5,
) -> float:
    """Quote-weighted spread across the top ``depth_levels`` of the book.

    ``bid_prices`` / ``ask_prices`` / ``bid_qtys`` / ``ask_qtys`` are
    1-D arrays sorted from inside (best price) outward.
    """
    n = min(depth_levels, len(bid_prices), len(ask_prices))
    bp = bid_prices[:n].astype(float)
    ap = ask_prices[:n].astype(float)
    bq = bid_qtys[:n].astype(float)
    aq = ask_qtys[:n].astype(float)
    weights = (bq + aq) / (bq.sum() + aq.sum() + _EPS)
    return float(((ap - bp) * weights).sum())


def depth_slope(
    prices: np.ndarray,
    qtys: np.ndarray,
    mid_price: float,
) -> float:
    """Linear-regression slope of cumulative quantity vs |price - mid|.

    Higher slope = steeper book (more thin / illiquid).
    """
    if len(prices) < 2:
        return float("nan")
    x = np.abs(np.asarray(prices, dtype=float) - mid_price)
    y = np.cumsum(np.asarray(qtys, dtype=float))
    if x.std() < _EPS:
        return float("nan")
    cov = np.cov(x, y, ddof=0)
    return float(cov[0, 1] / (x.var() + _EPS))


def trade_flow_imbalance(
    buy_volume: pd.Series,
    sell_volume: pd.Series,
    window: int = 20,
) -> pd.Series:
    """Rolling normalized imbalance of trade flow.

    Equivalent to a rolling-window VPIN-without-bucketing: positive
    values indicate buyer-initiated flow dominance.
    """
    diff = buy_volume - sell_volume
    total = buy_volume + sell_volume
    rolling_diff = diff.rolling(window, min_periods=1).sum()
    rolling_total = total.rolling(window, min_periods=1).sum()
    return rolling_diff / rolling_total.where(rolling_total != 0, _EPS)


def vpin(
    buy_volume: pd.Series,
    sell_volume: pd.Series,
    n_buckets: int = 50,
) -> pd.Series:
    """Volume-synchronised probability of informed trading (Easley/López/O'Hara).

    Re-buckets trade flow into volume buckets of equal size so each
    bucket carries the same total volume; then returns the rolling mean
    absolute imbalance.
    """
    cum = (buy_volume + sell_volume).cumsum()
    if cum.iloc[-1] <= 0:
        return pd.Series(np.nan, index=buy_volume.index)
    bucket_size = cum.iloc[-1] / n_buckets
    bucket_idx = (cum / bucket_size).astype(int)
    bucket_buy = buy_volume.groupby(bucket_idx).sum()
    bucket_sell = sell_volume.groupby(bucket_idx).sum()
    bucket_imbalance = (bucket_buy - bucket_sell).abs() / (bucket_buy + bucket_sell + _EPS)
    rolling = bucket_imbalance.rolling(min(50, len(bucket_imbalance)), min_periods=1).mean()
    return rolling.reindex(bucket_idx.values).set_axis(buy_volume.index)


def midprice(bid_price: Any, ask_price: Any) -> Any:
    """Plain ``(bid + ask) / 2`` mid price."""
    return (bid_price + ask_price) / 2.0


def spread(bid_price: Any, ask_price: Any) -> Any:
    """Plain top-of-book spread."""
    return ask_price - bid_price


def relative_spread(bid_price: Any, ask_price: Any) -> Any:
    """Spread normalized by mid-price (basis-points-friendly)."""
    mid = midprice(bid_price, ask_price)
    if isinstance(mid, pd.Series):
        return (ask_price - bid_price) / mid.where(mid != 0, _EPS)
    return (ask_price - bid_price) / (mid + _EPS)


__all__ = [
    "depth_slope",
    "midprice",
    "microprice",
    "order_book_imbalance",
    "relative_spread",
    "spread",
    "trade_flow_imbalance",
    "vpin",
    "weighted_spread",
]
