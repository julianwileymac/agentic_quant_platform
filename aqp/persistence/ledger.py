"""LedgerWriter — the single entry point for writing to the Execution Ledger.

Agents, strategies, and brokers all call this so every decision in the
system is captured transactionally. The Meta-Agent queries this table.

Tenancy: callers pass a :class:`aqp.auth.context.RequestContext` (or any
object with ``owner_user_id``/``workspace_id``/``project_id`` attributes)
so every persisted row inherits the same ownership stamp. When no
context is provided the writer falls back to
:func:`aqp.auth.context.default_context`, which routes legacy single-tenant
flows to the ``default-*`` seed from migration 0017.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from aqp.core.types import OrderData, Signal, TradeData
from aqp.persistence.db import get_session
from aqp.persistence.models import Fill, LedgerEntry, OrderRecord, SignalEntry

logger = logging.getLogger(__name__)


def _default_ctx_safely() -> Any:
    """Lazy-import the auth default context. Lets this module import early
    in test fixtures that don't construct the auth package."""
    try:
        from aqp.auth.context import default_context

        return default_context()
    except Exception:  # pragma: no cover
        return None


class LedgerWriter:
    """Thin façade writing structured records to Postgres.

    Designed to be called from both sync (Celery) and async (FastAPI) paths
    via its sync methods — the blocking I/O is negligible for the ledger.

    The optional ``context`` keyword threads the active tenancy
    (``user_id``, ``workspace_id``, ``project_id``) onto every row written
    by this writer. Pass ``None`` to fall back to the local-first default
    context — useful for legacy CLI / scripted flows that haven't been
    plumbed through to the new auth deps yet.
    """

    def __init__(
        self,
        backtest_id: str | None = None,
        strategy_id: str | None = None,
        *,
        context: Any | None = None,
    ) -> None:
        self.backtest_id = backtest_id
        self.strategy_id = strategy_id
        self.context = context if context is not None else _default_ctx_safely()

    @property
    def owner_user_id(self) -> str | None:
        return getattr(self.context, "user_id", None)

    @property
    def workspace_id(self) -> str | None:
        return getattr(self.context, "workspace_id", None)

    @property
    def project_id(self) -> str | None:
        return getattr(self.context, "project_id", None)

    def _stamp(self, row: Any) -> Any:
        """Stamp a fresh ORM row with the active tenancy fields if absent."""
        if self.owner_user_id and getattr(row, "owner_user_id", None) in (None, ""):
            row.owner_user_id = self.owner_user_id
        if self.workspace_id and getattr(row, "workspace_id", None) in (None, ""):
            row.workspace_id = self.workspace_id
        if self.project_id and hasattr(row, "project_id") and getattr(row, "project_id", None) in (None, ""):
            row.project_id = self.project_id
        return row

    # --- generic ----
    def log(
        self,
        entry_type: str,
        message: str,
        payload: dict[str, Any] | None = None,
        level: str = "info",
    ) -> str:
        entry = self._stamp(
            LedgerEntry(
                backtest_id=self.backtest_id,
                strategy_id=self.strategy_id,
                entry_type=entry_type,
                level=level,
                message=message,
                payload=payload or {},
                created_at=datetime.utcnow(),
            )
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
        row = self._stamp(
            SignalEntry(
                strategy_id=self.strategy_id,
                backtest_id=self.backtest_id,
                vt_symbol=signal.symbol.vt_symbol,
                direction=signal.direction.value,
                strength=float(signal.strength),
                confidence=float(signal.confidence),
                rationale=signal.rationale,
                created_at=signal.timestamp,
            )
        )
        with get_session() as session:
            session.add(row)
            session.flush()
            self._audit(session, "SIGNAL", f"signal {signal.symbol.vt_symbol} {signal.direction.value}",
                        {"id": row.id, "strength": signal.strength})
            return row.id

    # --- order ----
    def record_order(self, order: OrderData) -> str:
        row = self._stamp(
            OrderRecord(
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
        )
        with get_session() as session:
            session.add(row)
            session.flush()
            self._audit(session, "ORDER", f"order {order.symbol.vt_symbol} {order.side.value}",
                        {"order_id": order.order_id, "quantity": order.quantity})
            return row.id

    # --- fill ----
    def record_fill(self, trade: TradeData) -> str:
        row = self._stamp(
            Fill(
                order_id=None,
                vt_symbol=trade.symbol.vt_symbol,
                side=trade.side.value,
                quantity=float(trade.quantity),
                price=float(trade.price),
                commission=float(trade.commission),
                slippage=float(trade.slippage),
                created_at=trade.timestamp,
            )
        )
        with get_session() as session:
            session.add(row)
            session.flush()
            self._audit(session, "FILL", f"fill {trade.symbol.vt_symbol} {trade.side.value}@{trade.price}",
                        {"quantity": trade.quantity, "commission": trade.commission})
            return row.id

    # --- helpers ----
    def _audit(self, session, entry_type: str, message: str, payload: dict[str, Any]) -> None:
        entry = self._stamp(
            LedgerEntry(
                backtest_id=self.backtest_id,
                strategy_id=self.strategy_id,
                entry_type=entry_type,
                level="info",
                message=message,
                payload=payload,
                created_at=datetime.utcnow(),
            )
        )
        session.add(entry)
