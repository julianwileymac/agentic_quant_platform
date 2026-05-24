"""Event-sourced state for QuantBot Platform bots.

Four modules:

- :mod:`aqp_bots.state.store` — :class:`EventStore` writing through
  :class:`LedgerWriter` to the partitioned ``bot_events`` table.
- :mod:`aqp_bots.state.snapshots` — :class:`SnapshotWriter` periodic
  state checkpoints (replay anchors).
- :mod:`aqp_bots.state.projections` — CQRS read models (positions,
  pnl, exposure) rebuilt asynchronously from the event stream.
- :mod:`aqp_bots.state.replay` — `quantbot replay` time-travel
  debugging.
"""
from __future__ import annotations

from aqp_bots.state.projections import PnLProjection, PositionProjection
from aqp_bots.state.replay import ReplayCursor, replay_events
from aqp_bots.state.snapshots import SnapshotWriter
from aqp_bots.state.store import EventStore

__all__ = [
    "EventStore",
    "PnLProjection",
    "PositionProjection",
    "ReplayCursor",
    "SnapshotWriter",
    "replay_events",
]
