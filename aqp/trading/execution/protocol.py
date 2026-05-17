"""Phase 2 unified brokerage protocol operating on :class:`DomainOrder`.

The legacy :class:`aqp.core.interfaces.IBrokerage` /
:class:`IAsyncBrokerage` interfaces are kept unchanged. Phase 2 adds a
parallel :class:`IDomainBrokerage` ABC that operates on
:class:`DomainOrder` end-to-end. Concrete brokerages can implement both
during the migration window; the legacy adapter in
:mod:`aqp.trading.execution.legacy_adapter` bridges callers that still
speak ``OrderRequest`` to brokers that already speak ``DomainOrder``,
and vice versa.

The protocol declares the operations every Phase 2-aware broker MUST
support:

* ``submit(domain_order)`` -- submit a single :class:`DomainOrder`
* ``submit_list(order_list)`` -- submit a contingency list atomically
  (or raise / fall back to sequential submit with cleanup if atomic
  submission isn't supported by the venue)
* ``amend(...)`` -- in-place amendment that preserves queue position
  when the venue supports it (Phase 2 amendment manager handles the
  fallback to cancel + resubmit)
* ``cancel(...)`` -- cancel by client order id
* ``stream_execution_reports()`` -- async iterator of
  :class:`ExecutionReport` events
* ``fetch_open_orders()`` -- bulk REST poll used by the Phase 3
  reconciliation engine
* ``fetch_positions()`` -- bulk REST poll used by the reconciliation
  engine
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from decimal import Decimal

from aqp.core.domain.identifiers import ClientOrderId
from aqp.core.domain.orders import DomainOrder, OrderList


class IDomainBrokerage(ABC):
    """Async brokerage operating on :class:`DomainOrder` directly.

    Implementations also typically subclass the legacy
    :class:`aqp.core.interfaces.IAsyncBrokerage` so backtests + paper
    sessions can keep calling the older API while new code migrates.
    """

    name: str = "domain_brokerage"
    venue: str = "unknown"
    supports_websocket_amend: bool = False
    """Set True when the venue supports in-place amendment via WebSocket.

    When False, the amendment manager falls back to cancel + resubmit
    -- which loses queue position but is the safe default.
    """
    supports_oco: bool = False
    """Set True when the venue accepts an atomic OCO submission (e.g. Alpaca
    bracket orders, IBKR OCA groups). Otherwise the contingency manager
    simulates OCO by watching execution reports and emitting cancels.
    """
    supports_outside_rth: bool = False
    """Set True when the venue accepts an extended-hours flag."""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    async def connect_async(self) -> None: ...

    @abstractmethod
    async def disconnect_async(self) -> None: ...

    # ------------------------------------------------------------------
    # Order operations
    # ------------------------------------------------------------------

    @abstractmethod
    async def submit(self, order: DomainOrder) -> DomainOrder:
        """Submit a single order. Returns the order with venue ids stamped."""

    @abstractmethod
    async def submit_list(self, order_list: OrderList) -> OrderList:
        """Submit a contingency list. Returns the list with venue ids stamped.

        Implementations MUST emit a venue-specific atomic submission
        when ``supports_oco`` is True for OCO lists; otherwise they MUST
        accept the list and rely on the contingency manager to enforce
        the relationships via execution-report-driven cancels.
        """

    @abstractmethod
    async def amend(
        self,
        client_order_id: ClientOrderId,
        *,
        quantity: Decimal | None = None,
        price: Decimal | None = None,
        trigger_price: Decimal | None = None,
    ) -> DomainOrder:
        """Amend an order in place. Preserves queue position when supported."""

    @abstractmethod
    async def cancel(self, client_order_id: ClientOrderId) -> bool:
        """Cancel an order. Returns True on accepted cancel."""

    # ------------------------------------------------------------------
    # Stream + bulk poll (reconciliation surface)
    # ------------------------------------------------------------------

    @abstractmethod
    def stream_execution_reports(self):  # AsyncIterator[ExecutionReport]
        """Async iterator yielding execution reports as they arrive."""

    @abstractmethod
    async def fetch_open_orders(self) -> list[DomainOrder]:
        """REST poll: every order the venue has open for the account."""

    @abstractmethod
    async def fetch_positions(self) -> list[dict]:
        """REST poll: every position the venue knows about for the account.

        Returns a list of dicts matching the
        :class:`aqp.trading.reconciliation.PositionStatusReport` shape
        Phase 3 will define. For Phase 2 the dict carries
        ``(vt_symbol, position_side, quantity, average_entry_price)``.
        """


__all__ = ["IDomainBrokerage"]
