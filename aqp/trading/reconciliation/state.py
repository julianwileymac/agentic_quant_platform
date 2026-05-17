"""State value objects for the reconciliation engine.

The composite key the engine indexes by is
``(account_id, venue, vt_symbol, position_side)``. Every external-side
report and every local-cache row maps onto this key; matching is
done by membership in the state map.

The map is intentionally a plain dict keyed by the composite tuple so
the engine stays simple and testable. Concurrent writes are
serialised by the caller (the engine runs single-threaded per
account during a reconcile pass).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class CompositeKey:
    """The deterministic claim-mapping key.

    Four components:

    1. ``account_id`` -- venue-natural account id (Alpaca-PAPER-xxx,
       IBKR-DU12345)
    2. ``venue`` -- venue code (alpaca, ibkr, binance, ...)
    3. ``vt_symbol`` -- platform-canonical instrument symbol
    4. ``position_side`` -- ``net`` (netting mode) | ``long`` |
       ``short`` (hedging mode)

    The Nautilus #4012 failure mode (last-write-wins by instrument id
    alone) is closed because the same instrument under two different
    accounts becomes two distinct keys.
    """

    account_id: str
    venue: str
    vt_symbol: str
    position_side: str = "net"


@dataclass(slots=True)
class PositionStatusReport:
    """One row in a venue's reply to "tell me every position you carry".

    Plain dataclass (rather than a Pydantic model) so it stays
    Celery-pickleable. ``venue_position_id`` is the venue's stable id
    for the position -- the engine uses it as the natural key when
    minting an external claim row, never a fresh UUID.
    """

    account_id: str
    venue: str
    vt_symbol: str
    position_side: str
    quantity: float
    average_entry_price: float | None = None
    market_price: float | None = None
    unrealized_pnl: float | None = None
    realized_pnl: float | None = None
    leverage: float | None = None
    liquidation_price: float | None = None
    currency: str | None = None
    venue_position_id: str | None = None
    snapshot_ts: datetime = field(default_factory=datetime.utcnow)
    meta: dict[str, Any] = field(default_factory=dict)

    def key(self) -> CompositeKey:
        return CompositeKey(
            account_id=self.account_id,
            venue=self.venue,
            vt_symbol=self.vt_symbol,
            position_side=self.position_side or "net",
        )


@dataclass(slots=True)
class CachePositionSnapshot:
    """The reconciliation engine's view of a cached position.

    Built from :class:`aqp.persistence.models_accounts.AccountPositionRow`
    so the engine doesn't have to import ORM rows directly into its
    matching logic.
    """

    account_id: str
    venue: str
    vt_symbol: str
    position_side: str
    quantity: float
    average_entry_price: float | None = None
    pk: str | None = None  # primary key of the underlying ORM row

    def key(self) -> CompositeKey:
        return CompositeKey(
            account_id=self.account_id,
            venue=self.venue,
            vt_symbol=self.vt_symbol,
            position_side=self.position_side or "net",
        )


class ReconciliationStateMap:
    """Composite-key indexed map of position state.

    Iterating the map yields ``(CompositeKey, value)`` pairs sorted by
    key. The engine builds two maps (cache, venue) and walks the union
    of their keys to find anomalies.
    """

    def __init__(self) -> None:
        self._rows: dict[CompositeKey, Any] = {}

    def __setitem__(self, key: CompositeKey, value: Any) -> None:
        self._rows[key] = value

    def __getitem__(self, key: CompositeKey) -> Any:
        return self._rows[key]

    def __contains__(self, key: CompositeKey) -> bool:
        return key in self._rows

    def __iter__(self):
        return iter(sorted(self._rows.keys(), key=lambda k: (k.account_id, k.venue, k.vt_symbol, k.position_side)))

    def __len__(self) -> int:
        return len(self._rows)

    def keys(self):
        return list(self)

    def get(self, key: CompositeKey, default: Any = None) -> Any:
        return self._rows.get(key, default)

    def items(self):
        for key in self:
            yield key, self._rows[key]


__all__ = [
    "CachePositionSnapshot",
    "CompositeKey",
    "PositionStatusReport",
    "ReconciliationStateMap",
]
