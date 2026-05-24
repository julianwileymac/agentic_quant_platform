"""CQRS read-model projections from the event stream.

Strategy writes events; this module materializes derived views:

- :class:`PositionProjection` — net position by ``(venue, symbol)``
- :class:`PnLProjection` — realized / unrealized PnL per position
- :class:`ExposureProjection` — gross / net exposure by asset class

Projections are rebuilt asynchronously from the event log so the hot
write path stays fast. The kernel exposes a `/state/projections` REST
hook (Phase 12) that returns the current materialized view.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _PositionRow:
    venue: str
    symbol: str
    qty: Decimal = Decimal("0")
    avg_price: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")


class PositionProjection:
    """Net position per ``(venue, symbol)`` from the fill stream.

    The projection is idempotent under event replay so a partial replay
    converges on the same value as the full replay.
    """

    def __init__(self) -> None:
        self._rows: dict[str, _PositionRow] = {}

    def apply_fill(
        self,
        *,
        venue: str,
        symbol: str,
        side: str,
        qty: Decimal,
        price: Decimal,
    ) -> None:
        key = f"{venue}:{symbol}"
        row = self._rows.get(key)
        signed = qty if side == "buy" else -qty
        if row is None:
            self._rows[key] = _PositionRow(
                venue=venue, symbol=symbol, qty=signed, avg_price=price
            )
            return
        new_qty = row.qty + signed
        # Increasing exposure same side -> volume-weighted avg.
        # Reducing exposure -> realize PnL, leave avg.
        if (row.qty >= 0 and signed > 0) or (row.qty <= 0 and signed < 0):
            total_abs = abs(row.qty) + abs(signed)
            new_avg = (
                (row.avg_price * abs(row.qty) + price * abs(signed)) / total_abs
                if total_abs > 0
                else price
            )
            row.avg_price = new_avg
        else:
            # Reduction; realize PnL on the offset chunk.
            offset = min(abs(row.qty), abs(signed))
            if row.qty > 0:
                # Long position being reduced — PnL is sell_price - avg.
                row.realized_pnl += offset * (price - row.avg_price)
            else:
                row.realized_pnl += offset * (row.avg_price - price)
        row.qty = new_qty
        if new_qty == 0:
            row.avg_price = Decimal("0")

    def snapshot(self) -> dict[str, dict[str, str]]:
        return {
            key: {
                "venue": row.venue,
                "symbol": row.symbol,
                "qty": str(row.qty),
                "avg_price": str(row.avg_price),
                "realized_pnl": str(row.realized_pnl),
            }
            for key, row in self._rows.items()
        }


class PnLProjection:
    """Aggregate realized + unrealized PnL.

    Unrealized PnL requires a mark-to-market price from the data layer;
    callers pass the current mark in :meth:`mark` to refresh unrealized.
    """

    def __init__(self, *, position: PositionProjection) -> None:
        self.position = position
        self._unrealized: dict[str, Decimal] = {}

    def mark(self, venue: str, symbol: str, mark_price: Decimal) -> None:
        key = f"{venue}:{symbol}"
        row = self.position._rows.get(key)
        if row is None or row.qty == 0:
            self._unrealized.pop(key, None)
            return
        # Sign convention: long unrealized = (mark - avg) * qty.
        self._unrealized[key] = row.qty * (mark_price - row.avg_price)

    def snapshot(self) -> dict[str, Any]:
        realized = sum(
            (row.realized_pnl for row in self.position._rows.values()),
            start=Decimal("0"),
        )
        unrealized = sum(self._unrealized.values(), start=Decimal("0"))
        return {
            "realized": str(realized),
            "unrealized": str(unrealized),
            "total": str(realized + unrealized),
            "by_key": {
                key: {
                    "realized": str(row.realized_pnl),
                    "unrealized": str(self._unrealized.get(key, Decimal("0"))),
                }
                for key, row in self.position._rows.items()
            },
        }


@dataclass(slots=True)
class ExposureProjection:
    """Gross / net exposure aggregated across positions."""

    gross_usd: Decimal = Decimal("0")
    net_usd: Decimal = Decimal("0")

    def refresh(self, position: PositionProjection) -> None:
        gross = Decimal("0")
        net = Decimal("0")
        for row in position._rows.values():
            notional = abs(row.qty) * row.avg_price
            gross += notional
            net += row.qty * row.avg_price
        self.gross_usd = gross
        self.net_usd = net


__all__ = ["ExposureProjection", "PnLProjection", "PositionProjection"]
