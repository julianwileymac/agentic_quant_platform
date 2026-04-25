"""Backtest result handler (Lean ``BacktestingResultHandler``).

Collects equity samples, trades, and log messages as the engine replays
bars. Mirrors the pattern Lean uses so both the event-driven backtester
and the async paper session share a stats surface.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from aqp.core.interfaces import IResultHandler
from aqp.core.types import OrderEvent, OrderTicket, PositionData


@dataclass
class BacktestingResultHandler(IResultHandler):
    """Accumulates samples + events; produces a stats dict on ``finalize``."""

    equity_samples: list[tuple[datetime, float]] = field(default_factory=list)
    trade_events: list[OrderEvent] = field(default_factory=list)
    orders: list[OrderTicket] = field(default_factory=list)
    logs: list[tuple[str, str]] = field(default_factory=list)
    position_snapshots: list[tuple[datetime, list[dict[str, Any]]]] = field(default_factory=list)

    def on_sample(
        self,
        timestamp: datetime,
        equity: float,
        cash: float,
        positions: list[PositionData],
    ) -> None:
        self.equity_samples.append((timestamp, float(equity)))
        self.position_snapshots.append(
            (
                timestamp,
                [
                    {
                        "vt_symbol": p.symbol.vt_symbol,
                        "quantity": p.quantity,
                        "average_price": p.average_price,
                        "direction": p.direction.value,
                    }
                    for p in positions
                ],
            )
        )

    def on_trade(self, ticket: OrderTicket, event: OrderEvent) -> None:
        self.trade_events.append(event)

    def on_order(self, ticket: OrderTicket) -> None:
        self.orders.append(ticket)

    def on_log(self, level: str, message: str) -> None:
        self.logs.append((level, message))

    def finalize(self) -> dict[str, Any]:
        if not self.equity_samples:
            return {"samples": 0, "orders": 0, "fills": 0}
        equity = pd.Series(
            [e for _, e in self.equity_samples],
            index=pd.to_datetime([t for t, _ in self.equity_samples]),
        )
        returns = equity.pct_change().dropna()
        n_fills = sum(1 for e in self.trade_events if e.is_fill)
        return {
            "samples": len(self.equity_samples),
            "orders": len(self.orders),
            "fills": n_fills,
            "final_equity": float(equity.iloc[-1]),
            "return_pct": float((equity.iloc[-1] / equity.iloc[0]) - 1),
            "mean_daily_return": float(returns.mean()) if not returns.empty else 0.0,
            "vol_daily_return": float(returns.std()) if not returns.empty else 0.0,
        }
