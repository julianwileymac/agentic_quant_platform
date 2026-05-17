# Accounts, balances, positions

> Status: **Phase 3 shipped** (Alembic 0042 + 0043). Three new tables
> replace the in-memory ``AccountData`` snapshot.

## Three tables, three layers of granularity

```text
accounts                (id, account_id, venue, oms_type, ...)
   |
   +-- account_balances    (per currency + balance_kind)
   |
   +-- account_positions   (per (venue, vt_symbol, position_side))
```

### accounts

One row per (venue, brokerage account). The natural key
``(venue, account_id)`` matches the venue's own id, so the
reconciliation engine doesn't need an extra lookup to route external
events.

Columns of note:

* ``account_type`` -- ``cash | margin | portfolio_margin | futures |
  crypto_spot | crypto_deriv | betting``
* ``oms_type`` -- ``netting`` (single net position per instrument) or
  ``hedging`` (simultaneous long + short). Set once at account
  creation; can't switch mid-session.
* ``allow_cash_positions`` -- when False, fiat cash + spot crypto
  are treated as margin collateral, not as positions
* ``base_currency`` -- the currency every PnL number is normalised to

### account_balances

One row per ``(currency, balance_kind)``. The legacy single ``cash``
float is gone; the risk engine now reads explicit balance kinds:

* ``CASH``
* ``MARGIN_INITIAL`` / ``MARGIN_MAINTENANCE``
* ``BUYING_POWER``
* ``EXCESS_LIQUIDITY``
* ``UNREALIZED_PNL`` / ``REALIZED_PNL_DAY``
* ``WITHDRAWABLE`` / ``LOCKED``

A USD-denominated margin account at IBKR with $50k cash and $20k margin
used carries:

```text
(account, USD, CASH, 50000)
(account, USD, MARGIN_INITIAL, 20000)
(account, USD, BUYING_POWER, 80000)
```

### account_positions

One row per ``(venue, vt_symbol, position_side)``. Hedge-mode venues
(Binance, Bybit) carry simultaneous LONG and SHORT rows; netting
venues use ``position_side='net'`` and have one row per instrument.

Why this matters: the report cites
[Nautilus #4012](https://github.com/nautechsystems/nautilus_trader/issues/4012)
where keying state by instrument id alone caused last-write-wins
overwrites. The Phase 3 composite key
``(account_pk, venue, vt_symbol, position_side)`` closes that.

## Code example

```python
from datetime import datetime
from aqp.persistence.db import get_session
from aqp.persistence.models_accounts import (
    AccountRow,
    AccountBalanceRow,
    AccountPositionRow,
)

with get_session() as session:
    account = AccountRow(
        account_id="DU12345",
        venue="ibkr",
        account_type="margin",
        oms_type="netting",
        base_currency="USD",
        is_paper=True,
    )
    session.add(account)
    session.flush()  # populate account.id

    session.add(AccountBalanceRow(
        account_pk=account.id,
        currency="USD",
        balance_kind="CASH",
        amount=50_000.0,
        snapshot_ts=datetime.utcnow(),
    ))
    session.add(AccountPositionRow(
        account_pk=account.id,
        venue="ibkr",
        vt_symbol="AAPL.NASDAQ",
        position_side="net",
        quantity=100.0,
        average_entry_price=190.0,
        snapshot_ts=datetime.utcnow(),
    ))
```

## Hedge vs netting

When an account has ``oms_type='hedging'``, the position rows split:

```text
(account, BINANCE, BTCUSDT.BINANCE, long, +5)
(account, BINANCE, BTCUSDT.BINANCE, short, +3)
```

Net position is `+2` but the venue tracks both legs independently
(margin is computed per leg). The reconciliation engine handles each
row separately, so a partial fill on the LONG leg doesn't touch the
SHORT leg.

When ``oms_type='netting'``, only one row per instrument exists, and
new fills net against it:

```text
(account, ALPACA, AAPL.NASDAQ, net, +100)
```

A sell of 30 shares brings quantity to +70; a sell of 150 shares
flips to -50.

## Risk integration

The Phase 3 :class:`RiskManager.check_pretrade_v2` reads all three
tables to compute:

* Current equity (sum of CASH + UNREALIZED_PNL across currencies,
  FX-converted to ``base_currency``)
* Margin used (sum of MARGIN_INITIAL)
* Position-pct (current notional / equity)
* Gross exposure (sum of |notional| across positions / equity)
* Concentration (target notional / gross book)

All five limits are now enforced at submit time -- the pre-Phase-3
gap (only kill-switch + position-pct) is closed.
