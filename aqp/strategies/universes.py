"""Universe-selection models (Lean stage 1).

Includes static + volume-driven selectors plus a quarterly-rotation
universe (ported from FinRL-Trading's ``UniverseManager``) that drives a
daily universe from quarterly stock-selection results aligned to a
trading calendar.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from aqp.core.interfaces import IUniverseSelectionModel
from aqp.core.registry import register
from aqp.core.types import Exchange, Symbol

logger = logging.getLogger(__name__)


@register("StaticUniverse")
class StaticUniverse(IUniverseSelectionModel):
    """Hard-coded list of tickers. The simplest possible universe."""

    def __init__(self, symbols: Iterable[str], exchange: str = Exchange.NASDAQ.value) -> None:
        self.exchange = Exchange(exchange)
        self._symbols = [Symbol(ticker=s, exchange=self.exchange) for s in symbols]

    def select(self, timestamp: datetime, context: dict[str, Any]) -> list[Symbol]:
        return list(self._symbols)


@register("TopVolumeUniverse")
class TopVolumeUniverse(IUniverseSelectionModel):
    """Dynamic: select top-N symbols by trailing 20-day average volume."""

    def __init__(self, n: int = 20, lookback_days: int = 20) -> None:
        self.n = n
        self.lookback_days = lookback_days

    def select(self, timestamp: datetime, context: dict[str, Any]) -> list[Symbol]:
        bars = context.get("bars")
        if bars is None or bars.empty:
            return []
        recent = bars[
            (bars["timestamp"] <= timestamp)
            & (bars["timestamp"] >= timestamp.normalize() - pd.Timedelta(days=self.lookback_days))  # type: ignore
        ]
        ranked = (
            recent.groupby("vt_symbol")["volume"]
            .mean()
            .sort_values(ascending=False)
            .head(self.n)
            .index
        )
        return [Symbol.parse(s) for s in ranked]


# local import kept out of top-level to avoid pandas import on every load
try:  # pragma: no cover
    import pandas as pd  # noqa: F401
except ImportError:  # pragma: no cover
    pass


@register("QuarterlyRotationUniverse")
class QuarterlyRotationUniverse(IUniverseSelectionModel):
    """Build a daily universe from a quarterly stock-selection table.

    Pattern adapted from `FinRL-X
    <https://github.com/AI4Finance-Foundation/FinRL-Trading>`_'s
    ``UniverseManager``: each row in ``selection_df`` represents a stock
    that was picked on ``trade_date``; on the **next** trading day the
    stock becomes active and stays active until the next quarterly
    selection (or ``backtest_end``).

    Constructor args
    ----------------
    selection_df:
        Pandas DataFrame with at minimum two columns named
        ``trade_date`` and ``tic_name`` (override via ``column_map``).
    column_map:
        Optional dict to remap source columns, e.g.
        ``{"trade_date": "selection_date", "tic_name": "ticker"}``.
    trading_calendar:
        Sortable list of ``datetime``-like trading sessions. When ``None``
        the universe falls back to using ``selection_df.trade_date``
        as both pick and activation dates.
    backtest_start / backtest_end:
        Optional inclusive window applied to the selection rows. The
        active membership extends through to the next pick or
        ``backtest_end`` (or one day past the calendar's max).
    exchange:
        Default exchange used to materialise ``Symbol`` objects.
    """

    def __init__(
        self,
        selection_df: Any | None = None,
        column_map: dict[str, str] | None = None,
        trading_calendar: Iterable[datetime] | None = None,
        backtest_start: str | None = None,
        backtest_end: str | None = None,
        exchange: str = Exchange.NASDAQ.value,
    ) -> None:
        import pandas as pd  # heavy dep; lazy import keeps registry cheap

        self.exchange = Exchange(exchange)
        self._cache: dict[pd.Timestamp, set[str]] = {}
        self._dates_sorted: list[pd.Timestamp] = []

        if selection_df is None:
            return

        col_map = dict(column_map or {})
        col_trade = col_map.get("trade_date", "trade_date")
        col_tic = col_map.get("tic_name", "tic_name")

        df = selection_df.rename(columns={col_trade: "trade_date", col_tic: "tic_name"})
        if "trade_date" not in df.columns or "tic_name" not in df.columns:
            raise ValueError(
                "QuarterlyRotationUniverse requires `trade_date` and `tic_name` columns "
                "(use column_map to rename source columns)."
            )

        df = df[["trade_date", "tic_name"]].dropna()
        df["trade_date"] = pd.to_datetime(df["trade_date"])

        if backtest_start:
            df = df[df["trade_date"] >= pd.to_datetime(backtest_start)]
        if backtest_end:
            df = df[df["trade_date"] <= pd.to_datetime(backtest_end)]

        df = df.sort_values(["trade_date", "tic_name"])
        if df.empty:
            return

        if trading_calendar is not None:
            calendar = pd.DatetimeIndex(sorted(pd.to_datetime(list(trading_calendar))))
        else:
            calendar = pd.DatetimeIndex(sorted(df["trade_date"].unique()))

        if len(calendar) == 0:
            return

        # Compute activation = next trading day; deactivation = next activation.
        sel_dates = sorted(df["trade_date"].unique())
        act_dates: list[pd.Timestamp] = []
        for d in sel_dates:
            pos = calendar.searchsorted(d, side="right")
            act_dates.append(calendar[pos] if pos < len(calendar) else None)  # type: ignore[arg-type]

        deactivate_map: dict[pd.Timestamp, pd.Timestamp] = {}
        last_session = calendar.max() + pd.Timedelta(days=1)
        for i, ad in enumerate(act_dates):
            if ad is None:
                continue
            deactivate_map[ad] = act_dates[i + 1] if i + 1 < len(act_dates) and act_dates[i + 1] is not None else last_session  # type: ignore[index]

        cache: dict[pd.Timestamp, set[str]] = {}
        for sel_date, group in df.groupby("trade_date"):
            pos = calendar.searchsorted(sel_date, side="right")
            if pos >= len(calendar):
                continue
            ad = calendar[pos]
            de = deactivate_map.get(ad, last_session)
            tickers = list(group["tic_name"].astype(str))
            mask = (calendar >= ad) & (calendar < de)
            for active_day in calendar[mask]:
                cache.setdefault(pd.Timestamp(active_day), set()).update(tickers)

        self._cache = cache
        self._dates_sorted = sorted(cache.keys())

    def select(self, timestamp: datetime, context: dict[str, Any]) -> list[Symbol]:
        import pandas as pd

        if not self._cache:
            return []
        ts = pd.Timestamp(timestamp).normalize()
        tickers = self._cache.get(ts)
        if tickers is None:
            # Fall back to last <= ts
            idx = max(
                (i for i, d in enumerate(self._dates_sorted) if d <= ts),
                default=None,
            )
            if idx is None:
                return []
            tickers = self._cache.get(self._dates_sorted[idx], set())
        return [Symbol(ticker=t, exchange=self.exchange) for t in sorted(tickers)]
