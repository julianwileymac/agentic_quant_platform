---
title: 'Legacy `aqp.core.types` shim'
summary: 'The legacy module is imported by **~140 files** across the codebase (strategies, brokers, REST routes, paper-trading session, backtest engines, RL apps, tests). A hard delete would break every one of ...'
owner: platform-team
last_reviewed: 2026-05-25
audience: both
---

# Legacy `aqp.core.types` shim

> Status: **Phase 5 finalization shipped**. The module is now a thin
> compatibility shim over [`aqp.core.domain`](../aqp/core/domain/).

## Why a shim and not a delete

The legacy module is imported by **~140 files** across the codebase
(strategies, brokers, REST routes, paper-trading session, backtest
engines, RL apps, tests). A hard delete would break every one of them
in the same commit.

The shim approach preserves backward compatibility while making the
domain types the recommended path:

1. **Every public name still imports** -- no breaking change for the
   140 existing importers.
2. **Each domain-replaceable class is marked DEPRECATED** in its
   docstring with a `.. deprecated:: 5.0` Sphinx directive pointing
   at the canonical type.
3. **Bridge methods** on each legacy class let callers convert to the
   domain shape with one method call:
   * `Symbol.to_instrument_id()`
   * `OrderRequest.to_domain_order(client_order_id=, account=)`
   * `OrderData.to_domain_order()` / `OrderData.from_domain_order(...)`
   * `TradeData.from_execution_report(...)`
   * `PositionData.from_account_position_row(...)`
   * `AccountData.from_account_row(account_row, balances=...)`
4. **Domain re-exports at module bottom** let callers migrate one
   import at a time -- `from aqp.core.types import DomainOrder`
   works without rewriting the import line.

## Three categories of type

### Category 1 -- Domain replacement available

| Legacy | Domain canonical |
| --- | --- |
| `Symbol` | `aqp.core.domain.identifiers.InstrumentId` |
| `Exchange` | `aqp.core.domain.identifiers.Venue` (string-valued ID) |
| `AssetClass` | `aqp.core.domain.enums.AssetClass` (richer) |
| `SecurityType` | `aqp.core.domain.enums.InstrumentClass` |
| `OrderType` | `aqp.core.domain.enums.OrderType` (superset) |
| `OrderSide` | `aqp.core.domain.enums.OrderSide` (superset) |
| `OrderStatus` | `aqp.core.domain.enums.OrderStatus` (superset) |
| `Direction` | `aqp.core.domain.enums.PositionSide` |
| `OrderRequest` | `aqp.core.domain.orders.DomainOrder` |
| `OrderData` | `aqp.core.domain.orders.DomainOrder` |
| `AccountData` | `aqp.persistence.models_accounts.AccountRow` + balances |
| `PositionData` | `aqp.persistence.models_accounts.AccountPositionRow` |
| `TradeData` | `aqp.trading.execution.ExecutionReport` |

The legacy classes in this category are shims. Their docstring carries
`.. deprecated:: 5.0` and points at the canonical type.

### Category 2 -- Authoritative here (no domain replacement)

Market-data records and data-plane routing have no domain equivalents
because the domain layer is about identity / orders / accounts, not
the data plane:

* `BarData`, `TradeBar` (alias), `QuoteBar`, `TickData`, `Tick` (alias)
* `SubscriptionDataConfig`, `Interval`, `Resolution`, `TickType`,
  `DataNormalizationMode`

Framework value objects for the alpha / portfolio stages:

* `Signal`, `PortfolioTarget`

Backtest event-loop types:

* `Event`, `EventType`, `MarketEvent`, `SignalEvent`,
  `OrderEvent_Msg`, `FillEvent_Msg`

Legacy framework patterns for the existing `PaperTradingSession`:

* `OrderEvent` (state-transition record, NOT the messaging event),
  `OrderTicket`, `SecurityHolding`, `Cash`, `CashBook`

These types remain authoritative here.

### Category 3 -- Domain re-exports

Every Phase 1-5 domain type is re-exported from `aqp.core.types` so
callers can incrementally migrate. The recommended long-term migration
is `from aqp.core.domain import ...`, but the shim re-exports let you
do it one import line at a time:

```python
# Both work after Phase 5. The second is the recommended long-term form.
from aqp.core.types import DomainOrder, InstrumentId, OmsType
from aqp.core.domain import DomainOrder, InstrumentId, OmsType
```

The re-exports cover every name from
[`aqp/core/domain/enums.py`](../aqp/core/domain/enums.py),
[`aqp/core/domain/identifiers.py`](../aqp/core/domain/identifiers.py),
and [`aqp/core/domain/orders.py`](../aqp/core/domain/orders.py).

Names that would collide with the legacy enums get a `Domain` prefix:

| Legacy | Domain re-export |
| --- | --- |
| `OrderType` | `DomainOrderType` |
| `OrderSide` | `DomainOrderSide` |
| `OrderStatus` | `DomainOrderStatus` |
| `AssetClass` | `DomainAssetClass` |
| `AccountType` (legacy doesn't exist) | `DomainAccountType` |

Everything else (`InstrumentId`, `ClientOrderId`, `OrderListId`,
`DomainOrder`, `LimitOrder`, `StopMarketOrder`, `OrderList`,
`PositionSide`, `OmsType`, `ContingencyType`, `TriggerType`,
`TimeInForce`, `TrailingOffsetType`, `InstrumentClass`,
`LiquiditySide`, `AggressorSide`, ...) is re-exported under its
original name.

## Migration workflow

For a file currently using legacy types:

1. **Drop in domain bridges where convenient.** No import changes
   needed:

   ```python
   from aqp.core.types import OrderRequest

   req = OrderRequest(...)
   domain = req.to_domain_order()  # bridge to canonical
   ```

2. **Switch single imports incrementally.** Replace one legacy import
   at a time with the domain re-export through the shim:

   ```python
   # Before
   from aqp.core.types import OrderType, OrderSide, OrderStatus

   # After (works today, no functional change)
   from aqp.core.types import (
       DomainOrderType as OrderType,
       DomainOrderSide as OrderSide,
       DomainOrderStatus as OrderStatus,
   )
   ```

3. **Final form -- direct from domain.** Once the entire file is
   migrated, drop the shim:

   ```python
   from aqp.core.domain.enums import OrderType, OrderSide, OrderStatus
   ```

## Why we keep the legacy enums (instead of aliasing to domain)

The temptation is "just `OrderType = DomainOrderType`". We don't,
because:

* **Existing DB rows persist the legacy string values.** The legacy
  enum has `STOP = "stop"`; the domain has `STOP_MARKET = "stop_market"`.
  Renaming the enum would invalidate every previously-saved
  ``order_type`` column.
* **YAML strategy configs use the legacy values.** Backward compat
  with shipped strategy YAML is a hard requirement.
* **Some legacy values have NO domain equivalent.** `OrderStatus.NEW`
  (legacy) maps to `OrderStatus.ACCEPTED` (domain) but the legacy
  state machine has a different topology (no PENDING_UPDATE /
  PENDING_CANCEL).

The legacy enums are therefore kept verbatim; the deprecation
directive points callers at the richer domain enum, and the
re-exports give callers an opt-in path.

## When the shim can finally be deleted

The shim file disappears when:

1. Every importer has migrated to `from aqp.core.domain import ...`
2. Every persisted legacy enum value has been migrated to the
   domain canonical (`stop` -> `stop_market`, `cancelled` ->
   `canceled`, `new` -> `accepted`, `partial` -> `partially_filled`)
3. Every shipped YAML strategy config has been rewritten to use the
   domain values

That migration is a separate, multi-PR effort tracked outside this
Phase 5 finalization. The shim stays put until it's done.

## Bridge method reference

```python
from aqp.core.types import (
    Symbol, OrderRequest, OrderData, TradeData,
    PositionData, AccountData,
)

# Symbol <-> InstrumentId
sym = Symbol.parse("AAPL.NASDAQ")
iid = sym.to_instrument_id()
back = Symbol.from_instrument_id(iid)

# OrderRequest -> DomainOrder
req = OrderRequest(symbol=sym, side=..., order_type=..., quantity=10)
domain = req.to_domain_order(client_order_id="cl-1", gateway="alpaca")

# OrderData round-trip
data = OrderData(...)
domain = data.to_domain_order()
rebuilt = OrderData.from_domain_order(domain, gateway="alpaca")

# TradeData from ExecutionReport
from aqp.trading.execution import ExecutionReport
trade = TradeData.from_execution_report(report)

# PositionData from AccountPositionRow
from aqp.persistence.models_accounts import AccountPositionRow
pos = PositionData.from_account_position_row(row)

# AccountData snapshot from persistence rows
from aqp.persistence.models_accounts import AccountRow, AccountBalanceRow
snapshot = AccountData.from_account_row(account_row, balances=balance_rows)
```
