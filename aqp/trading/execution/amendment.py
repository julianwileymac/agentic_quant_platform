"""Order amendment with queue-position preservation.

The report's [Nautilus WebSocket amendment pattern](
https://github.com/nautechsystems/nautilus_trader/issues/4000) calls for
an atomic per-request counter mapped to a concurrent state table so a
caller can submit an in-place ``amend`` over a persistent WebSocket
connection and preserve the order's position in the limit order book
queue.

This module ships the Python equivalent: a thread-safe atomic counter
:class:`AtomicRequestIdCounter` (using :class:`threading.Lock` +
:class:`itertools.count`) and a manager :class:`AmendmentManager` that
decides whether each amendment can flow as an in-place WS amend or has
to fall back to cancel + resubmit.

The decision is per-broker and per-field:

* Quantity reductions on a limit order with the same price -- WS amend
  on Kraken / IBKR / Alpaca (queue preserved)
* Quantity increases -- venue-specific. Most venues require a fresh
  submission, which loses queue position.
* Price changes -- always treated as cancel + resubmit because the
  modified order takes the back of the queue at the new price.
* Trigger-price changes (stop / trailing-stop orders) -- WS amend on
  every supporting venue because the resting order isn't on the book
  yet; queue position doesn't apply.
"""
from __future__ import annotations

import itertools
import logging
import threading
import time
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any

from aqp.core.domain.enums import OrderType
from aqp.core.domain.identifiers import ClientOrderId
from aqp.core.domain.orders import DomainOrder

logger = logging.getLogger(__name__)


class AmendmentRouting(StrEnum):
    """How a single amendment request was routed."""

    WS_AMEND = "ws_amend"
    REST_AMEND = "rest_amend"
    CANCEL_RESUBMIT = "cancel_resubmit"
    REJECTED = "rejected"


@dataclass(slots=True)
class AtomicRequestIdCounter:
    """Thread-safe monotonic int64 counter.

    Python lacks an unsigned 64-bit primitive, but the
    :class:`threading.Lock` + :class:`itertools.count` pattern produces
    the same gap-free monotonic ids the Rust ``AtomicU64`` counter does.
    Each ``next_id()`` call is atomic.
    """

    _start: int = 1
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _counter: Any = None  # itertools.count instance

    def __post_init__(self) -> None:
        # itertools.count is its own iterator; ``next()`` is the
        # atomic increment. ``count(start)`` returns ``start, start+1, ...``
        # the first time and subsequent calls.
        self._counter = itertools.count(int(self._start))

    def next_id(self) -> int:
        with self._lock:
            return next(self._counter)


@dataclass(slots=True)
class AmendmentRequest:
    """Single amendment intent.

    At least one of the optional fields must be non-None. The validator
    in :meth:`AmendmentManager.amend` enforces this.
    """

    client_order_id: ClientOrderId
    quantity: Decimal | None = None
    price: Decimal | None = None
    trigger_price: Decimal | None = None

    def has_change(self) -> bool:
        return any(
            v is not None
            for v in (self.quantity, self.price, self.trigger_price)
        )


@dataclass(slots=True)
class AmendmentResult:
    """Result of an amendment dispatch."""

    request_id: int
    routing: AmendmentRouting
    order: DomainOrder | None = None
    error: str | None = None
    elapsed_ms: float = 0.0


class AmendmentManager:
    """Decide WS-amend vs cancel-resubmit per amendment.

    The manager doesn't talk to the venue directly -- it uses two
    awaitables wired in at construction time (``ws_amend`` and
    ``cancel_resubmit``) so the same logic can be unit-tested against
    mocks. Real brokers pass their own
    :meth:`IDomainBrokerage.amend` + ``cancel`` + ``submit`` triple.

    Per-broker policy lives in the broker adapter:
    :attr:`AmendmentManager._policy` is a dict
    ``{(field_name): bool}`` declaring whether each field is amendable
    in place. Quantity-down is the canonical example -- usually True;
    price changes are usually False.
    """

    def __init__(
        self,
        *,
        ws_amend: Any,
        cancel_resubmit: Any,
        rest_amend: Any | None = None,
        policy: dict[str, bool] | None = None,
    ) -> None:
        self._ws_amend = ws_amend
        self._rest_amend = rest_amend
        self._cancel_resubmit = cancel_resubmit
        # Default policy: only stop-trigger amendments are guaranteed
        # in-place. Quantity reductions on limit orders are also in-
        # place on Kraken / IBKR; brokers override per their venue.
        self._policy = policy or {
            "quantity_down": True,
            "quantity_up": False,
            "price": False,
            "trigger_price": True,
        }
        self._counter = AtomicRequestIdCounter()
        self._inflight: dict[int, ClientOrderId] = {}

    @property
    def policy(self) -> dict[str, bool]:
        return dict(self._policy)

    async def amend(
        self,
        request: AmendmentRequest,
        *,
        current_order: DomainOrder,
    ) -> AmendmentResult:
        """Dispatch ``request`` to ``current_order``."""
        start = time.monotonic()
        request_id = self._counter.next_id()
        self._inflight[request_id] = request.client_order_id
        try:
            if not request.has_change():
                return AmendmentResult(
                    request_id=request_id,
                    routing=AmendmentRouting.REJECTED,
                    error="empty amendment request -- no fields specified",
                )

            # Determine the routing by walking each requested change in
            # priority order:
            routes = self._select_routing(request, current_order)
            if routes is AmendmentRouting.REJECTED:
                return AmendmentResult(
                    request_id=request_id,
                    routing=AmendmentRouting.REJECTED,
                    error="all requested changes are policy-disallowed",
                )

            if routes is AmendmentRouting.WS_AMEND:
                try:
                    result = await self._ws_amend(request, current_order)
                    elapsed = (time.monotonic() - start) * 1000.0
                    return AmendmentResult(
                        request_id=request_id,
                        routing=AmendmentRouting.WS_AMEND,
                        order=result,
                        elapsed_ms=elapsed,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "WS amend failed, falling back to cancel+resubmit: %s",
                        exc,
                    )
                    # Fall through to cancel+resubmit
                    routes = AmendmentRouting.CANCEL_RESUBMIT

            if routes is AmendmentRouting.REST_AMEND and self._rest_amend is not None:
                try:
                    result = await self._rest_amend(request, current_order)
                    elapsed = (time.monotonic() - start) * 1000.0
                    return AmendmentResult(
                        request_id=request_id,
                        routing=AmendmentRouting.REST_AMEND,
                        order=result,
                        elapsed_ms=elapsed,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "REST amend failed, falling back to cancel+resubmit: %s",
                        exc,
                    )
                    routes = AmendmentRouting.CANCEL_RESUBMIT

            # Fallback: cancel + resubmit
            try:
                result = await self._cancel_resubmit(request, current_order)
                elapsed = (time.monotonic() - start) * 1000.0
                return AmendmentResult(
                    request_id=request_id,
                    routing=AmendmentRouting.CANCEL_RESUBMIT,
                    order=result,
                    elapsed_ms=elapsed,
                )
            except Exception as exc:  # noqa: BLE001
                elapsed = (time.monotonic() - start) * 1000.0
                return AmendmentResult(
                    request_id=request_id,
                    routing=AmendmentRouting.REJECTED,
                    error=f"cancel+resubmit failed: {exc}",
                    elapsed_ms=elapsed,
                )
        finally:
            self._inflight.pop(request_id, None)

    def _select_routing(
        self,
        request: AmendmentRequest,
        current_order: DomainOrder,
    ) -> AmendmentRouting:
        """Pick the right routing strategy for ``request``."""
        # 1. Stop-trigger price changes are almost always WS-amendable
        #    because the order isn't on the book yet.
        if request.trigger_price is not None and self._policy.get(
            "trigger_price", True
        ):
            return AmendmentRouting.WS_AMEND

        # 2. Quantity-down amendments preserve queue position when the
        #    venue supports them.
        if (
            request.quantity is not None
            and current_order.order_type
            in (OrderType.LIMIT, OrderType.STOP_LIMIT)
        ):
            new_qty = request.quantity
            if new_qty < current_order.remaining_quantity:
                if self._policy.get("quantity_down", True):
                    return AmendmentRouting.WS_AMEND
            elif self._policy.get("quantity_up", False):
                return AmendmentRouting.WS_AMEND

        # 3. Price changes -- the modified order goes to the back of the
        #    queue at the new price, so a cancel + resubmit is correct.
        if request.price is not None:
            return AmendmentRouting.CANCEL_RESUBMIT

        # 4. Anything we didn't cover -> cancel + resubmit as the safe
        #    default.
        return AmendmentRouting.CANCEL_RESUBMIT


__all__ = [
    "AmendmentManager",
    "AmendmentRequest",
    "AmendmentResult",
    "AmendmentRouting",
    "AtomicRequestIdCounter",
]
