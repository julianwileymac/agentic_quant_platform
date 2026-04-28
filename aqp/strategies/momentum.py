"""Cross-sectional momentum alpha."""
from __future__ import annotations

from typing import Any

import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol
from aqp.observability import get_tracer

_tracer = get_tracer("aqp.strategies.momentum")


@register("MomentumAlpha")
class MomentumAlpha(IAlphaModel):
    """Long top-quantile trailing returns, short (or flat) bottom quantile."""

    def __init__(
        self,
        lookback: int = 90,
        top_quantile: float = 0.3,
        bottom_quantile: float = 0.3,
        allow_short: bool = False,
    ) -> None:
        self.lookback = int(lookback)
        self.top_q = float(top_quantile)
        self.bottom_q = float(bottom_quantile)
        self.allow_short = bool(allow_short)

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        with _tracer.start_as_current_span("strategy.momentum.generate_signals") as span:
            try:
                span.set_attribute("strategy.lookback", self.lookback)
                span.set_attribute("strategy.universe_size", len(universe))
                span.set_attribute("strategy.bars_count", int(len(bars)))
            except Exception:
                pass
            return self._generate_signals_impl(bars, universe, context)

    def _generate_signals_impl(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        if bars.empty:
            return []

        universe_set = {s.vt_symbol for s in universe}
        now = context.get("current_time")

        records: list[tuple[str, float, pd.Timestamp]] = []
        for vt_symbol, sub in bars.groupby("vt_symbol", sort=False):
            if vt_symbol not in universe_set:
                continue
            sub = sub.sort_values("timestamp")
            if len(sub) < self.lookback + 1:
                continue
            ret = sub["close"].iloc[-1] / sub["close"].iloc[-self.lookback - 1] - 1
            records.append((vt_symbol, float(ret), sub["timestamp"].iloc[-1]))

        if not records:
            return []

        frame = pd.DataFrame(records, columns=["vt_symbol", "ret", "timestamp"])
        top_cut = frame["ret"].quantile(1 - self.top_q)
        bot_cut = frame["ret"].quantile(self.bottom_q)

        signals: list[Signal] = []
        for _, row in frame.iterrows():
            if row["ret"] >= top_cut:
                signals.append(
                    Signal(
                        symbol=Symbol.parse(row["vt_symbol"]),
                        strength=min(1.0, float(row["ret"])),
                        direction=Direction.LONG,
                        timestamp=now or row["timestamp"],
                        confidence=0.7,
                        horizon_days=21,
                        source="MomentumAlpha",
                        rationale=f"trailing {self.lookback}d return={row['ret']:.2%}",
                    )
                )
            elif self.allow_short and row["ret"] <= bot_cut:
                signals.append(
                    Signal(
                        symbol=Symbol.parse(row["vt_symbol"]),
                        strength=min(1.0, float(-row["ret"])),
                        direction=Direction.SHORT,
                        timestamp=now or row["timestamp"],
                        confidence=0.7,
                        horizon_days=21,
                        source="MomentumAlpha",
                        rationale=f"trailing {self.lookback}d return={row['ret']:.2%}",
                    )
                )
        return signals
