"""LedgerWriter — the single entry point for writing to the Execution Ledger.

Agents, strategies, and brokers all call this so every decision in the
system is captured transactionally. The Meta-Agent queries this table.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from aqp.core.types import OrderData, Signal, TradeData
from aqp.persistence.db import get_session
from aqp.persistence.models import Fill, LedgerEntry, OrderRecord, SignalEntry

logger = logging.getLogger(__name__)


class LedgerWriter:
    """Thin façade writing structured records to Postgres.

    Designed to be called from both sync (Celery) and async (FastAPI) paths
    via its sync methods — the blocking I/O is negligible for the ledger.
    """

    def __init__(self, backtest_id: str | None = None, strategy_id: str | None = None) -> None:
        self.backtest_id = backtest_id
        self.strategy_id = strategy_id

    # --- generic ----
    def log(
        self,
        entry_type: str,
        message: str,
        payload: dict[str, Any] | None = None,
        level: str = "info",
    ) -> str:
        entry = LedgerEntry(
            backtest_id=self.backtest_id,
            strategy_id=self.strategy_id,
            entry_type=entry_type,
            level=level,
            message=message,
            payload=payload or {},
            created_at=datetime.utcnow(),
        )
        try:
            with get_session() as session:
                session.add(entry)
                session.flush()
                return entry.id
        except Exception:
            logger.exception("Failed to write ledger entry %s", entry_type)
            return ""

    # --- signal ----
    def record_signal(self, signal: Signal) -> str:
        row = SignalEntry(
            strategy_id=self.strategy_id,
            backtest_id=self.backtest_id,
            vt_symbol=signal.symbol.vt_symbol,
            direction=signal.direction.value,
            strength=float(signal.strength),
            confidence=float(signal.confidence),
            rationale=signal.rationale,
            created_at=signal.timestamp,
        )
        with get_session() as session:
            session.add(row)
            session.flush()
            self._audit(session, "SIGNAL", f"signal {signal.symbol.vt_symbol} {signal.direction.value}",
                        {"id": row.id, "strength": signal.strength})
            return row.id

    # --- order ----
    def record_order(self, order: OrderData) -> str:
        row = OrderRecord(
            strategy_id=self.strategy_id,
            backtest_id=self.backtest_id,
            vt_symbol=order.symbol.vt_symbol,
            side=order.side.value,
            order_type=order.order_type.value,
            quantity=float(order.quantity),
            price=float(order.price) if order.price is not None else None,
            status=order.status.value,
            reference=order.reference,
            created_at=order.created_at,
        )
        with get_session() as session:
            session.add(row)
            session.flush()
            self._audit(session, "ORDER", f"order {order.symbol.vt_symbol} {order.side.value}",
                        {"order_id": order.order_id, "quantity": order.quantity})
            return row.id

    # --- fill ----
    def record_fill(self, trade: TradeData) -> str:
        row = Fill(
            order_id=None,
            vt_symbol=trade.symbol.vt_symbol,
            side=trade.side.value,
            quantity=float(trade.quantity),
            price=float(trade.price),
            commission=float(trade.commission),
            slippage=float(trade.slippage),
            created_at=trade.timestamp,
        )
        with get_session() as session:
            session.add(row)
            session.flush()
            self._audit(session, "FILL", f"fill {trade.symbol.vt_symbol} {trade.side.value}@{trade.price}",
                        {"quantity": trade.quantity, "commission": trade.commission})
            return row.id

    # --- helpers ----
    def _audit(self, session, entry_type: str, message: str, payload: dict[str, Any]) -> None:
        entry = LedgerEntry(
            backtest_id=self.backtest_id,
            strategy_id=self.strategy_id,
            entry_type=entry_type,
            level="info",
            message=message,
            payload=payload,
            created_at=datetime.utcnow(),
        )
        session.add(entry)
