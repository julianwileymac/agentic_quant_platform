"""Lean-style ``Slice`` — the immutable snapshot of data for one time step.

A ``Slice`` bundles every piece of market data that arrived at a single
timestamp: trade bars, quote bars, ticks, and corporate actions. It is
the argument passed to ``IStrategy.on_data(slice, context)`` — the
Lean-style replacement for the older ``on_bar(bar, context)`` hook.

The backtest engine and the paper engine build one ``Slice`` per
replay step so strategies can treat a single bar and a panel of bars
the same way.
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from aqp.core.types import BarData, QuoteBar, Symbol, TickData


@dataclass(frozen=True)
class CorporateActionEvent:
    """A split, dividend, or delisting carried alongside price data."""

    symbol: Symbol
    timestamp: datetime
    kind: str  # "split" | "dividend" | "delisting" | "symbol_changed"
    value: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Slice:
    """Immutable container of everything that happened at ``timestamp``.

    Built by the engine before dispatching to the strategy. ``bars`` and
    ``quote_bars`` are keyed by ``vt_symbol`` for O(1) lookups.
    """

    timestamp: datetime
    bars: dict[str, BarData] = field(default_factory=dict)
    quote_bars: dict[str, QuoteBar] = field(default_factory=dict)
    ticks: dict[str, list[TickData]] = field(default_factory=dict)
    splits: dict[str, CorporateActionEvent] = field(default_factory=dict)
    dividends: dict[str, CorporateActionEvent] = field(default_factory=dict)
    delistings: dict[str, CorporateActionEvent] = field(default_factory=dict)

    # -- lookup helpers ---------------------------------------------------

    def __contains__(self, key: str | Symbol) -> bool:
        vt = key.vt_symbol if isinstance(key, Symbol) else str(key)
        return vt in self.bars or vt in self.quote_bars

    def bar(self, key: str | Symbol) -> BarData | None:
        vt = key.vt_symbol if isinstance(key, Symbol) else str(key)
        return self.bars.get(vt)

    def quote(self, key: str | Symbol) -> QuoteBar | None:
        vt = key.vt_symbol if isinstance(key, Symbol) else str(key)
        return self.quote_bars.get(vt)

    def price(self, key: str | Symbol) -> float | None:
        """Best-effort latest price: trade close → quote mid → tick last."""
        vt = key.vt_symbol if isinstance(key, Symbol) else str(key)
        bar = self.bars.get(vt)
        if bar is not None:
            return bar.close
        qb = self.quote_bars.get(vt)
        if qb is not None:
            return qb.mid_close
        tick_list = self.ticks.get(vt)
        if tick_list:
            return tick_list[-1].last
        return None

    def symbols(self) -> list[str]:
        """Every symbol touched by this slice, deduplicated."""
        keys: set[str] = set()
        keys.update(self.bars.keys())
        keys.update(self.quote_bars.keys())
        keys.update(self.ticks.keys())
        keys.update(self.splits.keys())
        keys.update(self.dividends.keys())
        keys.update(self.delistings.keys())
        return sorted(keys)

    @property
    def is_empty(self) -> bool:
        return not (self.bars or self.quote_bars or self.ticks)

    def __iter__(self) -> Iterator[tuple[str, BarData]]:
        """Iterate over ``(vt_symbol, bar)`` pairs — like Lean's ``Slice``."""
        yield from self.bars.items()

    # -- builders ---------------------------------------------------------

    @classmethod
    def from_bars(
        cls,
        timestamp: datetime,
        bars: Iterable[BarData],
    ) -> Slice:
        """Construct a slice from an iterable of ``BarData`` at one ``timestamp``."""
        bar_map = {b.vt_symbol: b for b in bars}
        return cls(timestamp=timestamp, bars=bar_map)

    def with_quote_bars(self, quote_bars: Iterable[QuoteBar]) -> Slice:
        """Return a new slice with quote bars merged in (immutable-ish)."""
        merged = {qb.vt_symbol: qb for qb in quote_bars}
        return Slice(
            timestamp=self.timestamp,
            bars=dict(self.bars),
            quote_bars={**self.quote_bars, **merged},
            ticks=dict(self.ticks),
            splits=dict(self.splits),
            dividends=dict(self.dividends),
            delistings=dict(self.delistings),
        )
