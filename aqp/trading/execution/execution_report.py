"""ExecutionReport DTO + dispatcher.

The :class:`ExecutionReport` dataclass is the in-memory representation
of one row in ``execution_reports`` -- the venue-stamped audit trail
introduced in Alembic migration 0041. Brokers emit
:class:`ExecutionReport` instances when a fill / cancel / rejection
arrives over the WebSocket; the dispatcher routes them to:

1. The persistence layer (writes one row in ``execution_reports``)
2. The :class:`aqp.trading.execution.contingency.ContingencyManager`
   (so OCO / OUO / OTO relationships fire)
3. The legacy session's order-event queue (so ``PaperTradingSession``
   keeps working unchanged)

The dispatcher is intentionally not a Celery worker: it runs in-process
in the execution loop so latency stays low. The persistence write is
fire-and-forget through a session.add + commit; the contingency
manager is synchronous.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from aqp.core.domain.enums import LiquiditySide, OrderSide, OrderStatus

logger = logging.getLogger(__name__)


class ReportKind(StrEnum):
    """Every state transition a venue can emit on a single order."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DENIED = "denied"
    SUBMITTED = "submitted"
    TRIGGERED = "triggered"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELED = "canceled"
    EXPIRED = "expired"
    UPDATED = "updated"
    PENDING_CANCEL = "pending_cancel"
    PENDING_UPDATE = "pending_update"
    MODIFY_REJECTED = "modify_rejected"
    EMULATED = "emulated"
    RELEASED = "released"


@dataclass
class ExecutionReport:
    """One execution event from a venue.

    Keyed by ``(venue, venue_execution_id)`` so the Phase 3
    reconciliation engine can deduplicate WS-vs-REST duplicates with
    a deterministic natural key.
    """

    venue: str
    venue_execution_id: str
    report_kind: ReportKind
    ts_event: datetime
    ts_received: datetime = field(default_factory=datetime.utcnow)

    venue_order_id: str | None = None
    client_order_id: str | None = None
    domain_order_id: str | None = None
    trade_id: str | None = None
    position_id: str | None = None
    account_id: str | None = None

    order_status: OrderStatus | None = None
    order_side: OrderSide | None = None
    last_quantity: Decimal | None = None
    last_price: Decimal | None = None
    cumulative_quantity: Decimal | None = None
    average_fill_price: Decimal | None = None
    commission: Decimal | None = None
    commission_currency: str | None = None
    liquidity_side: LiquiditySide | None = None
    reason: str | None = None
    seq_no: int | None = None

    vt_symbol: str | None = None
    workspace_id: str | None = None
    project_id: str | None = None
    experiment_id: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class ExecutionReportDispatcher:
    """Route :class:`ExecutionReport` events to persistence + contingency.

    Used in three contexts:

    1. **Live trading session** -- iterates ``stream_execution_reports``
       on the broker and calls :meth:`dispatch` for each event.
    2. **Backtest engine** -- builds synthetic reports for every fill
       and dispatches them so the same audit trail exists for
       backtests.
    3. **Reconciliation engine (Phase 3)** -- synthesises reports for
       any venue position / order that wasn't present locally, so the
       deterministic claim mapping algorithm has a single row to
       reference.
    """

    def __init__(
        self,
        *,
        contingency_manager: Any = None,
        persist: bool = True,
        on_command: Any = None,
    ) -> None:
        self._contingency = contingency_manager
        self._persist = persist
        self._on_command = on_command

    def dispatch(self, report: ExecutionReport) -> None:
        """Route ``report`` through persistence + contingency + callback."""
        if self._persist:
            self._persist_report(report)
        commands: list[Any] = []
        if self._contingency is not None and report.client_order_id and report.order_status:
            from aqp.core.domain.identifiers import ClientOrderId

            commands = self._contingency.on_execution_report(
                client_order_id=ClientOrderId(report.client_order_id),
                order_status=report.order_status,
                cumulative_quantity=report.cumulative_quantity,
                last_quantity=report.last_quantity,
            )
        if self._on_command is not None:
            for cmd in commands:
                try:
                    self._on_command(cmd)
                except Exception:  # noqa: BLE001
                    logger.exception("on_command callback failed")

    def _persist_report(self, report: ExecutionReport) -> None:
        """Insert one row into ``execution_reports``.

        Idempotent via the ``(venue, venue_execution_id)`` unique index.
        Duplicates (from WS-vs-REST races) are silently swallowed.
        """
        try:
            from aqp.persistence.db import get_session
            from aqp.persistence.models_orders import ExecutionReportRow

            with get_session() as session:
                row = ExecutionReportRow(
                    venue=report.venue,
                    venue_execution_id=report.venue_execution_id,
                    venue_order_id=report.venue_order_id,
                    account_id=report.account_id,
                    client_order_id=report.client_order_id,
                    domain_order_id=report.domain_order_id,
                    trade_id=report.trade_id,
                    position_id=report.position_id,
                    report_kind=report.report_kind.value
                    if isinstance(report.report_kind, ReportKind)
                    else str(report.report_kind),
                    order_status=(
                        report.order_status.value
                        if isinstance(report.order_status, OrderStatus)
                        else (str(report.order_status) if report.order_status else None)
                    ),
                    order_side=(
                        report.order_side.value
                        if isinstance(report.order_side, OrderSide)
                        else (str(report.order_side) if report.order_side else None)
                    ),
                    last_quantity=(
                        None if report.last_quantity is None else float(report.last_quantity)
                    ),
                    last_price=(
                        None if report.last_price is None else float(report.last_price)
                    ),
                    cumulative_quantity=(
                        None
                        if report.cumulative_quantity is None
                        else float(report.cumulative_quantity)
                    ),
                    average_fill_price=(
                        None
                        if report.average_fill_price is None
                        else float(report.average_fill_price)
                    ),
                    commission=(
                        None if report.commission is None else float(report.commission)
                    ),
                    commission_currency=report.commission_currency,
                    liquidity_side=(
                        report.liquidity_side.value
                        if isinstance(report.liquidity_side, LiquiditySide)
                        else (
                            str(report.liquidity_side)
                            if report.liquidity_side
                            else None
                        )
                    ),
                    reason=report.reason,
                    ts_event=report.ts_event,
                    ts_received=report.ts_received,
                    seq_no=report.seq_no,
                    workspace_id=report.workspace_id,
                    project_id=report.project_id,
                    experiment_id=report.experiment_id,
                    meta=dict(report.meta or {}),
                )
                session.add(row)
        except Exception as exc:  # noqa: BLE001
            # Duplicate-key races (WS + REST emit the same event) land
            # here; the unique index prevents double-insert. Log and
            # continue -- this is the documented behaviour.
            logger.debug("execution_report persist skipped: %s", exc)


__all__ = [
    "ExecutionReport",
    "ExecutionReportDispatcher",
    "ReportKind",
]
