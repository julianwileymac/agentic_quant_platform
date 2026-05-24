"""Phase 3: deterministic state reconciliation between cache + venue.

The reconciliation engine closes the well-known failure modes the
report cites:

* Nautilus #4012 -- assigning status reports by instrument id alone
  causes "last write wins" overwrites when one account holds two
  positions on the same instrument across sub-accounts.
* Nautilus #3176 -- minting fresh client UUIDs at boot for orders
  already known to the venue creates "phantom" orders that
  accumulate on every restart.

The fix is documented in detail in
[aqp_docs/reconciliation.md](../../aqp_docs/reconciliation.md): a
composite-key two-way reconciliation loop that bridges venue
positions/orders into the cache using the venue's natural id, never
a fresh client UUID.
"""
from __future__ import annotations

from aqp.trading.reconciliation.engine import (
    ReconciliationEngine,
    ReconciliationOutcome,
    ReconciliationStrategy,
)
from aqp.trading.reconciliation.state import (
    PositionStatusReport,
    ReconciliationStateMap,
)

__all__ = [
    "PositionStatusReport",
    "ReconciliationEngine",
    "ReconciliationOutcome",
    "ReconciliationStateMap",
    "ReconciliationStrategy",
]
