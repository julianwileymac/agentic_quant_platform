"""Data-plane routing — maps ``SubscriptionDataConfig`` to concrete providers.

Every data consumer in the platform (backtest engine, paper engine, RL
env, factor job) asks the ``SubscriptionManager`` for a history provider
or a streaming feed by handing it a ``SubscriptionDataConfig``. That
centralises the lookup so:

1. the user can swap a symbol from the Parquet lake to a local drive
   without touching strategy code;
2. the manager knows which resolution to route where (daily → DuckDB,
   minute → DuckDB if available, realtime → Alpaca/IBKR feed);
3. corporate-action normalisation is applied consistently.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

import pandas as pd

from aqp.core.interfaces import IHistoryProvider, IMarketDataFeed, ISubscriptionManager
from aqp.core.types import (
    DataNormalizationMode,
    Resolution,
    SubscriptionDataConfig,
    Symbol,
    TickType,
)

logger = logging.getLogger(__name__)


class SubscriptionManager(ISubscriptionManager):
    """Central routing table for ``SubscriptionDataConfig`` instances.

    Supply a primary history provider (usually ``DuckDBHistoryProvider``)
    and optionally a live feed factory; the manager hands out the right
    object per subscription.
    """

    def __init__(
        self,
        primary: IHistoryProvider,
        extra_providers: Iterable[IHistoryProvider] | None = None,
        live_feed_factory: Any = None,
    ) -> None:
        self.primary = primary
        self.extras: list[IHistoryProvider] = list(extra_providers or [])
        self.live_feed_factory = live_feed_factory
        self._subs: dict[str, SubscriptionDataConfig] = {}

    # -- ISubscriptionManager ---------------------------------------------

    def add(self, cfg: SubscriptionDataConfig) -> None:
        self._subs[cfg.vt_symbol] = cfg

    def remove(self, cfg: SubscriptionDataConfig) -> None:
        self._subs.pop(cfg.vt_symbol, None)

    def list(self) -> list[SubscriptionDataConfig]:
        return list(self._subs.values())

    def history_provider(self, cfg: SubscriptionDataConfig) -> IHistoryProvider:
        """Pick a history provider for this subscription."""
        # Higher resolutions or tick data could route elsewhere — for now
        # the primary DuckDB provider handles everything we ship. Keep the
        # hook open for custom routing.
        if cfg.resolution == Resolution.TICK:
            for provider in self.extras:
                if getattr(provider, "supports_ticks", False):
                    return provider
        return self.primary

    def live_feed(self, venue: str) -> IMarketDataFeed | None:
        """Build a live feed on demand (Alpaca / IBKR / polling)."""
        if self.live_feed_factory is None:
            return None
        return self.live_feed_factory(venue)

    # -- convenience ------------------------------------------------------

    def get_bars(
        self,
        symbols: Iterable[Symbol],
        start,
        end,
        interval: str = "1d",
        normalization: DataNormalizationMode = DataNormalizationMode.ADJUSTED,
    ) -> pd.DataFrame:
        """Unified bar query — routes through the primary provider."""
        provider = self.primary
        if hasattr(provider, "get_bars_normalized"):
            return provider.get_bars_normalized(
                symbols, start, end, interval=interval, normalization=normalization
            )
        return provider.get_bars(symbols, start, end, interval=interval)

    def describe(self) -> pd.DataFrame:
        """Summary of every registered subscription."""
        rows = []
        for cfg in self._subs.values():
            rows.append(
                {
                    "vt_symbol": cfg.vt_symbol,
                    "resolution": cfg.resolution.value,
                    "tick_type": cfg.tick_type.value,
                    "normalization": cfg.normalization.value,
                    "fill_forward": cfg.fill_forward,
                    "extended_hours": cfg.extended_hours,
                }
            )
        return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Convenience builder
# ---------------------------------------------------------------------------


def subscriptions_from_symbols(
    symbols: Iterable[Symbol | str],
    resolution: Resolution = Resolution.DAILY,
    normalization: DataNormalizationMode = DataNormalizationMode.ADJUSTED,
    tick_type: TickType = TickType.TRADE,
) -> list[SubscriptionDataConfig]:
    """Produce a default ``SubscriptionDataConfig`` per ticker string or ``Symbol``."""
    out: list[SubscriptionDataConfig] = []
    for s in symbols:
        sym = s if isinstance(s, Symbol) else Symbol.parse(str(s))
        out.append(
            SubscriptionDataConfig(
                symbol=sym,
                resolution=resolution,
                tick_type=tick_type,
                normalization=normalization,
            )
        )
    return out
