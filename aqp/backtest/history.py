"""Composite history provider (Lean ``HistoryProviderManager``)."""
from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime

import pandas as pd

from aqp.core.interfaces import IHistoryProvider
from aqp.core.types import Symbol

logger = logging.getLogger(__name__)


class HistoryProviderManager(IHistoryProvider):
    """Tries each registered provider in order until one returns data.

    Matches Lean's ``HistoryProviderManager`` semantics — lets the engine
    chain ``DuckDBHistoryProvider`` (disk) → broker history → vendor REST
    without the strategy caring which one answered.
    """

    def __init__(self, providers: Iterable[IHistoryProvider]) -> None:
        self.providers = list(providers)
        if not self.providers:
            raise ValueError("HistoryProviderManager requires at least one provider")

    def get_bars(
        self,
        symbols: Iterable[Symbol],
        start: datetime,
        end: datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        wanted = set(
            (s.vt_symbol if isinstance(s, Symbol) else str(s)) for s in symbols
        )
        frames: list[pd.DataFrame] = []
        remaining = set(wanted)
        for provider in self.providers:
            if not remaining:
                break
            try:
                df = provider.get_bars(
                    [Symbol.parse(v) for v in sorted(remaining)],
                    start,
                    end,
                    interval=interval,
                )
            except Exception:
                logger.exception("provider %s failed", type(provider).__name__)
                continue
            if df is None or df.empty:
                continue
            frames.append(df)
            remaining -= set(df["vt_symbol"].unique().tolist())
        if not frames:
            return pd.DataFrame()
        return (
            pd.concat(frames, ignore_index=True)
            .drop_duplicates(subset=["timestamp", "vt_symbol"])
            .sort_values(["timestamp", "vt_symbol"])
            .reset_index(drop=True)
        )
