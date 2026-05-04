"""Bar pivoting helpers for the vbt-pro engine.

vbt-pro consumes wide-format DataFrames (rows = timestamp, columns = vt_symbol)
for OHLCV inputs. AQP's canonical bar shape is tidy/long
(``timestamp, vt_symbol, open, high, low, close, volume``). These helpers
do the reshape once and centralise the convention so every vbt-pro caller
agrees on the resulting axis and ordering.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from aqp.core.types import Symbol


@dataclass(frozen=True)
class OHLCVPanel:
    """Wide-format OHLCV panel suitable for ``Portfolio.from_*`` constructors.

    Each frame has ``DatetimeIndex`` rows and ``vt_symbol`` columns. Missing
    bars are forward-filled at the close so vbt-pro never sees a NaN-aware
    branch in the inner Numba loop.
    """

    open: pd.DataFrame
    high: pd.DataFrame
    low: pd.DataFrame
    close: pd.DataFrame
    volume: pd.DataFrame

    @property
    def index(self) -> pd.DatetimeIndex:
        return self.close.index  # type: ignore[return-value]

    @property
    def columns(self) -> pd.Index:
        return self.close.columns

    def to_kwargs(self) -> dict[str, pd.DataFrame]:
        """Return the OHLC kwargs vbt-pro accepts on ``from_signals`` /
        ``from_orders`` (close is positional but other OHLC fields are kwargs)."""
        return {"open": self.open, "high": self.high, "low": self.low}


def pivot_close(bars: pd.DataFrame) -> pd.DataFrame:
    """Wide close panel ``[time, vt_symbol]`` with ``ffill`` applied."""
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    pivot = df.pivot_table(
        index="timestamp", columns="vt_symbol", values="close", aggfunc="last"
    )
    return pivot.sort_index().ffill()


def pivot_ohlcv(bars: pd.DataFrame) -> OHLCVPanel:
    """Wide OHLCV panel for the full surface of vbt-pro constructors.

    The resulting frames share the same index (timestamps) and columns
    (vt_symbols). Volume is NOT forward-filled — only OHLC.
    """
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    def _pivot(field: str, ffill: bool = False) -> pd.DataFrame:
        out = df.pivot_table(
            index="timestamp",
            columns="vt_symbol",
            values=field,
            aggfunc="last",
        ).sort_index()
        return out.ffill() if ffill else out.fillna(0.0)

    return OHLCVPanel(
        open=_pivot("open", ffill=True),
        high=_pivot("high", ffill=True),
        low=_pivot("low", ffill=True),
        close=_pivot("close", ffill=True),
        volume=_pivot("volume", ffill=False),
    )


def universe_from_bars(bars: pd.DataFrame) -> list[Symbol]:
    """Return the list of :class:`Symbol` instances present in ``bars``.

    Order is stable (sorted) so signal/order arrays line up deterministically
    across runs.
    """
    out: list[Symbol] = []
    for vt in sorted(bars["vt_symbol"].unique()):
        try:
            out.append(Symbol.parse(vt))
        except Exception:
            continue
    return out


def filter_bars(
    bars: pd.DataFrame,
    *,
    start: Any | None = None,
    end: Any | None = None,
) -> pd.DataFrame:
    """Apply optional ``start`` / ``end`` date filters to a tidy bars frame."""
    frame = bars.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    if start is not None:
        frame = frame[frame["timestamp"] >= pd.Timestamp(start)]
    if end is not None:
        frame = frame[frame["timestamp"] <= pd.Timestamp(end)]
    return frame.sort_values(["timestamp", "vt_symbol"]).reset_index(drop=True)


__all__ = [
    "OHLCVPanel",
    "pivot_close",
    "pivot_ohlcv",
    "universe_from_bars",
    "filter_bars",
]
