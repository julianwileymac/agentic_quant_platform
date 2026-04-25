"""Provider priority ladder — FMP → WRDS → Yahoo Finance.

FinRL-Trading's tutorials wrap their data fetcher in a cascade of
providers so users see the highest-quality data that their credentials
unlock. We implement the same pattern as a thin class over callables.

Every provider is represented by a :class:`ProviderAdapter` that knows
how to fetch bars for ``(symbols, start, end, interval)``. The ladder
tries each in order and returns the first non-empty result.

Adapters intentionally live in this module (not in
:mod:`aqp.data.ingestion`) so the ladder is easy to reuse standalone
without pulling the full ingestion stack. Users who need a different
order can construct a custom :class:`PriorityLadder` in their own code.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


FetchFn = Callable[[list[str], str, str, str], pd.DataFrame]


@dataclass
class ProviderAdapter:
    name: str
    fetch: FetchFn
    quality: int = 3  # 1 (low) .. 5 (high)
    requires_credentials: bool = False


@dataclass
class PriorityLadder:
    """Try adapters in order and return the first that yields rows."""

    adapters: list[ProviderAdapter] = field(default_factory=list)

    def fetch(
        self,
        symbols: list[str],
        start: datetime | str,
        end: datetime | str,
        interval: str = "1d",
    ) -> pd.DataFrame:
        start_str = str(start)
        end_str = str(end)
        for adapter in self.adapters:
            try:
                df = adapter.fetch(symbols, start_str, end_str, interval)
            except Exception as exc:
                logger.info("provider %s failed: %s", adapter.name, exc)
                continue
            if isinstance(df, pd.DataFrame) and not df.empty:
                logger.info(
                    "provider %s returned %d rows (quality=%d)",
                    adapter.name,
                    len(df),
                    adapter.quality,
                )
                df.attrs["provider"] = adapter.name
                return df
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Built-in adapters
# ---------------------------------------------------------------------------


def _yfinance_fetch(
    symbols: list[str],
    start: str,
    end: str,
    interval: str,
) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError:
        return pd.DataFrame()
    try:
        tickers = [s.split(".", 1)[0] for s in symbols]
        data = yf.download(
            tickers,
            start=start,
            end=end,
            interval=interval,
            progress=False,
            auto_adjust=False,
            group_by="ticker",
        )
    except Exception as exc:
        logger.info("yfinance fetch failed: %s", exc)
        return pd.DataFrame()
    if data is None or data.empty:
        return pd.DataFrame()

    rows: list[dict] = []
    if isinstance(data.columns, pd.MultiIndex):
        for ticker in tickers:
            try:
                sub = data[ticker].copy()
            except Exception:
                continue
            for ts, r in sub.iterrows():
                rows.append({
                    "timestamp": pd.Timestamp(ts),
                    "vt_symbol": f"{ticker}.NASDAQ",
                    "open": float(r.get("Open", 0.0)),
                    "high": float(r.get("High", 0.0)),
                    "low": float(r.get("Low", 0.0)),
                    "close": float(r.get("Close", 0.0)),
                    "volume": float(r.get("Volume", 0.0)),
                })
    else:
        for ts, r in data.iterrows():
            rows.append({
                "timestamp": pd.Timestamp(ts),
                "vt_symbol": f"{tickers[0]}.NASDAQ",
                "open": float(r.get("Open", 0.0)),
                "high": float(r.get("High", 0.0)),
                "low": float(r.get("Low", 0.0)),
                "close": float(r.get("Close", 0.0)),
                "volume": float(r.get("Volume", 0.0)),
            })
    return pd.DataFrame(rows)


def _fmp_fetch(
    symbols: list[str],
    start: str,
    end: str,
    interval: str,
) -> pd.DataFrame:
    """Stub — FMP integration is left for a follow-up PR.

    The function returns an empty frame so the ladder proceeds to the
    next provider. Wire up the real fetch when you add an FMP adapter.
    """
    return pd.DataFrame()


def _wrds_fetch(
    symbols: list[str],
    start: str,
    end: str,
    interval: str,
) -> pd.DataFrame:
    """Stub — WRDS integration is left for a follow-up PR."""
    return pd.DataFrame()


def default_ladder() -> PriorityLadder:
    """Return the default FinRL-Trading ladder (FMP → WRDS → Yahoo)."""
    return PriorityLadder(
        adapters=[
            ProviderAdapter(
                name="fmp",
                fetch=_fmp_fetch,
                quality=5,
                requires_credentials=True,
            ),
            ProviderAdapter(
                name="wrds",
                fetch=_wrds_fetch,
                quality=4,
                requires_credentials=True,
            ),
            ProviderAdapter(
                name="yfinance",
                fetch=_yfinance_fetch,
                quality=3,
                requires_credentials=False,
            ),
        ]
    )


__all__ = [
    "FetchFn",
    "PriorityLadder",
    "ProviderAdapter",
    "default_ladder",
]
