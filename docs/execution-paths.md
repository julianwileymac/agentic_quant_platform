# Execution paths: WebSocket priority + queue-preserving amendment

> Status: **Phase 2 shipped** (Alembic 0041). Amendment manager:
> [`aqp/trading/execution/amendment.py`](../aqp/trading/execution/amendment.py).

## Why WebSocket-first

The Nautilus issue [#4000](https://github.com/nautechsystems/nautilus_trader/issues/4000)
documents the cost of using REST for amendment: most REST `PATCH`
endpoints actually implement amendment as cancel + recreate. The
modified order takes a NEW venue order id and goes to the back of
the limit order book queue at the new price. For market-making
strategies this is a non-starter -- the queue position IS the alpha.

Phase 2's :class:`IDomainBrokerage` declares two capability flags:

* :attr:`IDomainBrokerage.supports_websocket_amend` -- the venue has a
  WS endpoint that modifies the order in place
* :attr:`IDomainBrokerage.supports_oco` -- the venue accepts an atomic
  OCO submission

When both are True, the broker is "Phase 2 ready" and the
:class:`AmendmentManager` routes:

| Change | WS amend supported | Routing |
| --- | --- | --- |
| Trigger price (stop / MIT / trailing-stop) | True | ``WS_AMEND`` |
| Trigger price | False | ``CANCEL_RESUBMIT`` |
| Quantity-down on limit | True | ``WS_AMEND`` |
| Quantity-up on limit | True (if policy allows) | ``WS_AMEND`` |
| Quantity-up on limit | False (default policy) | ``CANCEL_RESUBMIT`` |
| Price change | Any | ``CANCEL_RESUBMIT`` |

Price changes always go cancel + resubmit because the modified order
takes the back of the queue at the new price anyway.

## Atomic request id counter

The amendment manager's
:class:`aqp.trading.execution.amendment.AtomicRequestIdCounter` mirrors
Rust's ``AtomicU64`` via :class:`threading.Lock` +
:class:`itertools.count`. Each ``next_id()`` returns a monotonically
increasing 64-bit-safe int that the manager uses as the WS message id.

Why is this important?

* WebSocket amend / cancel messages are dispatched asynchronously --
  the response comes back over the same connection with the matching
  request id.
* If two amendments race (the strategy emits a new amendment before
  the previous one's response arrives), the manager needs to
  disambiguate which response belongs to which intent.
* The counter is gap-free under concurrency, so the matching state
  table stays correct even when 10+ amendments are inflight.

## Fallback semantics

When the WS amend fails (network drop, venue rejection, policy
disallowing the change), the manager:

1. Logs at WARNING level with the original exception.
2. Falls through to cancel + resubmit using the broker's
   :meth:`IDomainBrokerage.cancel` + :meth:`IDomainBrokerage.submit`.
3. Returns an :class:`AmendmentResult` with
   ``routing=CANCEL_RESUBMIT`` so the caller knows queue position was
   lost.

This is the "WS primary path with REST fallback" pattern from the
Nautilus issue. Callers don't have to know which route was used --
the result tells them.

## Code example

```python
from decimal import Decimal
from aqp.trading.execution import AmendmentManager, AmendmentRequest

mgr = AmendmentManager(
    ws_amend=broker.ws_amend,           # async callable
    cancel_resubmit=broker.cancel_resubmit,  # async callable
)

# Reduce a 10-lot limit order to 5 lots without losing queue position
result = await mgr.amend(
    AmendmentRequest(
        client_order_id=order.client_order_id,
        quantity=Decimal("5"),
    ),
    current_order=order,
)
print(result.routing, result.elapsed_ms)
```

## Persistence

Every amendment ultimately produces one or more
:class:`ExecutionReport` rows in ``execution_reports``. The
:class:`ExecutionReportDispatcher` writes them; the
``(venue, venue_execution_id)`` unique index dedupes duplicates from
the WS-vs-REST race.

## Broker capability matrix

| Broker | supports_websocket_amend | supports_oco | supports_outside_rth |
| --- | --- | --- | --- |
| Alpaca | True (TradingStream subscription) | True (bracket orders) | True (extended_hours flag) |
| IBKR | True (gateway native) | True (OCA groups) | True (outsideRth flag) |
| Tradier | False (REST-only amendment) | False | True (ext_hours flag) |
| Binance | True | False (simulated) | n/a (24x7 venue) |
| Kraken | True (4000 implementation) | False (simulated) | n/a |
| SimulatedBrokerage | True | True (manager-driven) | True |

The matrix is read at runtime from the broker's class attributes;
specific venues that ship later get added the same way.
