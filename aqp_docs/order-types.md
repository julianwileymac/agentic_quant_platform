# Order types

> Status: **Phase 2 shipped** (Alembic 0041). The :class:`DomainOrder`
> hierarchy in [`aqp/core/domain/orders.py`](../aqp/core/domain/orders.py)
> is now the canonical wire shape, persisted in ``domain_orders``.

## Why one canonical shape

The legacy stack used a flat :class:`OrderRequest` dataclass with five
fields plus a string ``time_in_force``. That worked for cash-equity
market and limit orders, but the report flagged a long list of order
shapes the platform needed to support before agents could route
serious capital:

* Stop-market, stop-limit, market-if-touched, limit-if-touched
* Trailing-stop variants (with offset type: price / bps / ticks /
  percentage)
* Iceberg orders (visible display quantity < total quantity)
* Post-only liquidity adds
* Reduce-only (Binance, Bybit, dYdX semantics)
* Close-position (Binance semantics; auto-closes the existing position)
* Outside-RTH (extended-hours on Alpaca, ``outsideRth`` on IBKR,
  ``ext_hours`` on Tradier)
* Algorithmic execution instructions (TWAP / VWAP / participation)
* OCO / OUO / OTO contingency lists

The Phase 2 unification settles all of these as fields on
:class:`DomainOrder` or as subclasses.

## Subclass tree

```text
DomainOrder
+-- MarketOrder
+-- LimitOrder (+ display_quantity for icebergs)
+-- StopMarketOrder
+-- StopLimitOrder (+ display_quantity)
+-- MarketIfTouchedOrder
+-- LimitIfTouchedOrder
+-- MarketToLimitOrder
+-- TrailingStopMarketOrder (trigger price + trailing offset + offset type)
+-- TrailingStopLimitOrder (trigger price + price + limit_offset + trailing_offset)
```

Every subclass inherits :class:`DomainOrder`'s flags:

* ``post_only`` -- add liquidity only; reject if it would cross
* ``reduce_only`` -- reduce existing position only; never flip net
* ``outside_rth`` -- allow execution outside regular trading hours
* ``close_position`` -- auto-close existing position (Binance-style)
* ``contingency_type`` + ``order_list_id`` + ``linked_order_ids`` --
  contingency graph linkage
* ``good_till_date`` -- TIF=GTD expiry

## Time in Force

| Value | Behaviour |
| --- | --- |
| ``DAY`` | Expires at session close (default) |
| ``GTC`` | Good 'til canceled |
| ``IOC`` | Immediate-or-cancel: fill any matchable size now, cancel rest |
| ``FOK`` | Fill-or-kill: fill 100% now, else cancel entire order |
| ``GTD`` | Good 'til date (``good_till_date`` field required) |
| ``AT_THE_OPEN`` | Send at session open |
| ``AT_THE_CLOSE`` | Send at session close |

## Trigger types

For stop / MIT / trailing-stop orders, the trigger price can be
referenced against different price types:

| Value | Compares against |
| --- | --- |
| ``DEFAULT`` | Venue default (usually LAST) |
| ``BID_ASK`` | Best bid (long) / best ask (short) |
| ``LAST_PRICE`` | Last trade |
| ``DOUBLE_LAST`` | Two consecutive last-trade prints |
| ``DOUBLE_BID_ASK`` | Two consecutive best bid / ask |
| ``LAST_OR_BID_ASK`` | Either last or top-of-book |
| ``MID_POINT`` | Mid (bid + ask) / 2 |
| ``MARK_PRICE`` | Mark price (futures-style) |
| ``INDEX_PRICE`` | Underlying index price |

## Trailing offsets

For trailing-stop orders, the offset can be:

| Value | Math |
| --- | --- |
| ``PRICE`` | Absolute price delta |
| ``BASIS_POINTS`` | bps applied to current price |
| ``TICKS`` | Tick-size multiples |
| ``PERCENTAGE`` | Percent of current price |

The trigger price recomputes as the favourable extreme of the price
trail; venues that don't natively support this (e.g. some crypto
exchanges) get a manager-driven simulation in the contingency manager.

## Flag exclusivity

The :meth:`DomainOrder.validate_flags` method enforces:

* ``reduce_only`` + ``close_position`` is rejected (mutually exclusive)
* ``post_only`` requires a non-``MARKET`` order_type
* ``TimeInForce.GTD`` requires ``good_till_date``
* ``quantity > 0`` unless ``close_position=True``

## Adding a new order subclass

1. Add the :class:`OrderType` enum value in
   [`aqp/core/domain/enums.py`](../aqp/core/domain/enums.py).
2. Add the :class:`DomainOrder` subclass in
   [`aqp/core/domain/orders.py`](../aqp/core/domain/orders.py).
3. If the type has its own typed columns (e.g. an exotic stop with
   a partial-trail mechanic), extend
   [`aqp/persistence/models_orders.py::DomainOrderRow`](../aqp/persistence/models_orders.py)
   and ship an Alembic migration.
4. Extend the legacy adapter mapping in
   [`aqp/trading/execution/legacy_adapter.py::_LEGACY_TO_DOMAIN_ORDER_TYPE`](../aqp/trading/execution/legacy_adapter.py).
5. Implement the venue-specific translation in each broker adapter
   that supports it; raise ``NotImplementedError`` on adapters that
   don't.
