"""Flat ``/orders`` surface used by the Vite Live Trading Desk.

The Live Desk in ``frontend/src/routes/live/page.tsx`` posts to a flat
``/orders`` REST surface (``POST /orders``, ``DELETE /orders/{id}``,
``GET /orders/working``) instead of the venue-scoped
``/brokers/{venue}/orders`` playground or the long-running ``/paper/*``
session loop.

This router is a thin wrapper:

- **POST /orders** — create an :class:`~aqp.persistence.models.OrderRecord`
  with ``reference="desk:manual"``. When ``paper=false`` we proxy the
  submission to the configured live brokerage venue (Alpaca by default)
  via :mod:`aqp.api.routes.brokers`. The simulated path persists the
  order as ``new`` so the desk's *Working orders* tab has a real row to
  display until it is cancelled.
- **DELETE /orders/{id}** — flips the order to ``cancelled``. For live
  orders we also fan out to the matching venue adapter.
- **GET /orders/working** — returns the open orders as
  :class:`WorkingOrderRow` instances matching the frontend's
  ``WorkingOrderRow`` interface.

All write paths consult :func:`aqp.risk.kill_switch.is_engaged` and
return HTTP 423 when the kill-switch is engaged, mirroring the
contract on ``/brokers/...``.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from aqp.api.security import secure_router
from aqp.config import settings
from aqp.core.types import OrderRequest, OrderSide, OrderType, Symbol
from aqp.persistence.db import get_session
from aqp.persistence.models import Fill, OrderRecord
from aqp.risk.kill_switch import is_engaged

logger = logging.getLogger(__name__)
router = secure_router(prefix="/orders", tags=["orders"], default_scope="trade:read")


_OPEN_STATUSES = {"submitting", "new", "partial", "partially_filled", "accepted"}


class CreateOrderRequest(BaseModel):
    """Frontend payload from ``OrderTicket``.

    Mirrors the ``SubmitPayload`` shape in
    ``frontend/src/components/live/OrderTicket.tsx``.
    """

    vt_symbol: str
    side: Literal["buy", "sell"]
    qty: float = Field(..., gt=0, description="Order quantity (positive)")
    order_type: Literal["market", "limit", "stop", "stop_limit"] = "market"
    paper: bool = True
    limit_price: float | None = None
    stop_price: float | None = None
    venue: str | None = Field(
        default=None,
        description="Optional explicit live venue. Defaults to AQP_DEFAULT_LIVE_VENUE / 'alpaca'.",
    )
    reference: str | None = Field(
        default="desk:manual",
        description="OrderRecord.reference value; use to attribute the order.",
    )


class CreateOrderResponse(BaseModel):
    order_id: str
    vt_symbol: str
    side: str
    order_type: str
    qty: float
    status: str
    paper: bool
    venue: str | None = None
    created_at: str


class WorkingOrderRow(BaseModel):
    """Matches ``frontend/src/components/live/WorkingOrders.tsx``."""

    id: str
    vt_symbol: str
    side: Literal["buy", "sell"]
    qty: float
    filled_qty: float = 0.0
    limit_price: float | None = None
    status: str
    created_at: str


def _coerce_symbol(vt_symbol: str) -> Symbol:
    if "." in vt_symbol:
        return Symbol.parse(vt_symbol)
    return Symbol(ticker=vt_symbol)


def _record_to_working_row(rec: OrderRecord, *, filled_qty: float = 0.0) -> WorkingOrderRow:
    return WorkingOrderRow(
        id=rec.id,
        vt_symbol=rec.vt_symbol,
        side="buy" if (rec.side or "").lower() == "buy" else "sell",
        qty=float(rec.quantity or 0.0),
        filled_qty=float(filled_qty),
        limit_price=rec.price,
        status=rec.status or "new",
        created_at=rec.created_at.isoformat() if rec.created_at else datetime.utcnow().isoformat(),
    )


def _resolve_live_venue(req: CreateOrderRequest) -> str:
    if req.venue:
        return req.venue.lower()
    # Pick the first configured live venue, falling back to alpaca.
    candidate = (
        getattr(settings, "default_live_venue", None)
        or "alpaca"
    )
    return str(candidate).lower()


def _persist_order_record(
    *,
    order_id: str,
    req: CreateOrderRequest,
    status: str,
) -> OrderRecord:
    rec = OrderRecord(
        id=order_id,
        vt_symbol=req.vt_symbol,
        side=req.side,
        order_type=req.order_type,
        quantity=float(req.qty),
        price=req.limit_price,
        status=status,
        reference=req.reference or "desk:manual",
        created_at=datetime.utcnow(),
    )
    with get_session() as s:
        s.add(rec)
    return rec


@router.post("", response_model=CreateOrderResponse)
async def create_order(req: CreateOrderRequest) -> CreateOrderResponse:
    """Create a manual order from the Live Desk ticket.

    For paper orders we persist an :class:`OrderRecord` directly with
    status ``new`` so it appears in *Working orders*. The simulated
    fills are produced by the long-running ``/paper/start`` session
    loop, not by this endpoint — the desk is intentionally an audit /
    visibility surface for ad-hoc tickets.

    For live orders (``paper=false``) we proxy to the configured live
    venue's ``submit_order`` via :mod:`aqp.api.routes.brokers` and
    persist the resulting ``order_id`` so the row shows up in the
    same working-orders list.
    """
    if is_engaged():
        raise HTTPException(status_code=423, detail="kill switch engaged — rejecting order")

    # Validate enums up front so 400s come back before any side effects.
    try:
        OrderSide(req.side)
        OrderType(req.order_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if req.paper:
        order_id = uuid.uuid4().hex[:12]
        rec = _persist_order_record(order_id=order_id, req=req, status="new")
        logger.info("paper order %s persisted: %s %s %s", order_id, req.side, req.qty, req.vt_symbol)
        return CreateOrderResponse(
            order_id=rec.id,
            vt_symbol=rec.vt_symbol,
            side=rec.side,
            order_type=rec.order_type,
            qty=float(rec.quantity),
            status=rec.status,
            paper=True,
            venue="simulated",
            created_at=rec.created_at.isoformat() if rec.created_at else datetime.utcnow().isoformat(),
        )

    # Live path: proxy to the per-venue brokerage adapter.
    venue = _resolve_live_venue(req)
    from aqp.api.routes.brokers import OrderForm, venue_submit_order

    form = OrderForm(
        symbol=req.vt_symbol,
        side=req.side,
        order_type=req.order_type,
        quantity=float(req.qty),
        price=req.limit_price,
        stop_price=req.stop_price,
    )
    try:
        result = await venue_submit_order(venue, form)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    venue_order_id = str(result.get("order_id") or uuid.uuid4().hex[:12])
    rec = _persist_order_record(
        order_id=venue_order_id,
        req=req,
        status=str(result.get("status") or "new"),
    )
    return CreateOrderResponse(
        order_id=rec.id,
        vt_symbol=rec.vt_symbol,
        side=rec.side,
        order_type=rec.order_type,
        qty=float(rec.quantity),
        status=rec.status,
        paper=False,
        venue=venue,
        created_at=rec.created_at.isoformat() if rec.created_at else datetime.utcnow().isoformat(),
    )


@router.delete("/{order_id}")
async def cancel_order(order_id: str) -> dict[str, Any]:
    """Cancel a working order and update its persisted status.

    For paper orders we just flip the ``OrderRecord.status`` to
    ``cancelled``. For live orders we additionally try the matching
    venue's ``cancel_order``; failures are surfaced but the persisted
    row is still flipped so the UI doesn't keep showing stale state.
    """
    with get_session() as s:
        rec = s.get(OrderRecord, order_id)
        if rec is None:
            raise HTTPException(status_code=404, detail=f"no such order: {order_id}")
        was_status = rec.status
        rec.status = "cancelled"
        venue = None
        # ``reference`` shape is ``"desk:manual"`` (paper) or
        # ``"venue:<name>"`` for live (set when the live path lands;
        # extension point for future bookkeeping).
        if rec.reference and rec.reference.startswith("venue:"):
            venue = rec.reference.split(":", 1)[1]

    extra: dict[str, Any] = {"order_id": order_id, "previous_status": was_status, "cancelled": True}
    if venue:
        try:
            from aqp.api.routes.brokers import venue_cancel_order

            extra.update(await venue_cancel_order(venue, order_id))
        except HTTPException as exc:
            extra["venue_error"] = exc.detail
        except Exception as exc:  # noqa: BLE001
            extra["venue_error"] = str(exc)
    return extra


@router.get("/working", response_model=list[WorkingOrderRow])
def list_working(limit: int = 50) -> list[WorkingOrderRow]:
    """Return open orders, newest first.

    Open == ``status in {submitting, new, partial, partially_filled,
    accepted}``. The list is bounded to ``limit`` rows (default 50)
    so a long history of cancelled tickets never blocks the UI.
    """
    with get_session() as s:
        rows: list[OrderRecord] = list(
            s.execute(
                select(OrderRecord)
                .where(OrderRecord.status.in_(_OPEN_STATUSES))
                .order_by(desc(OrderRecord.created_at))
                .limit(max(1, min(limit, 500)))
            )
            .scalars()
            .all()
        )
        if not rows:
            return []
        order_ids = [r.id for r in rows]
        # Aggregate filled quantity per order so the UI can show
        # progress. ``Fill`` rows are persisted by the paper session
        # loop and the broker adapter wrappers.
        fills_by_order: dict[str, float] = {}
        if order_ids:
            fill_rows = list(
                s.execute(
                    select(Fill.order_id, Fill.quantity).where(Fill.order_id.in_(order_ids))
                ).all()
            )
            for oid, q in fill_rows:
                if oid is None:
                    continue
                fills_by_order[oid] = fills_by_order.get(oid, 0.0) + float(q or 0.0)
        return [
            _record_to_working_row(r, filled_qty=fills_by_order.get(r.id, 0.0))
            for r in rows
        ]


__all__ = [
    "router",
    "CreateOrderRequest",
    "CreateOrderResponse",
    "WorkingOrderRow",
]
