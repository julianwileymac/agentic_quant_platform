"""Periodic state snapshot writer.

Lets the kernel rebuild in-memory state on restart in O(snapshot_size +
events_since_snapshot) rather than O(all_events). The kernel calls
:meth:`SnapshotWriter.write` on its ``state_layer.snapshot_interval_seconds``
cadence.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SnapshotPayload:
    """One snapshot's full payload."""

    bot_id: str
    seq_no: int
    snapshot_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    run_id: str | None = None
    positions: dict[str, Any] = field(default_factory=dict)
    exposures: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    raw_state: dict[str, Any] = field(default_factory=dict)


class SnapshotWriter:
    """Persists :class:`SnapshotPayload` to ``bot_snapshots``.

    Reuses :class:`LedgerWriter` for tenancy stamping (rule 34); never
    blocks the trading thread (caller dispatches to a worker).
    """

    def __init__(self, *, bot_id: str, context: Any | None = None) -> None:
        self.bot_id = bot_id
        self.context = context

    def write(self, payload: SnapshotPayload) -> str | None:
        """Persist ``payload``. Returns the snapshot row id (or None on failure)."""
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.ledger import LedgerWriter
            from aqp.persistence.models_bots import BotSnapshot
        except Exception:  # noqa: BLE001
            return None

        writer = LedgerWriter(context=self.context)
        try:
            with SessionLocal() as session:
                row = BotSnapshot(
                    bot_id=payload.bot_id,
                    run_id=payload.run_id,
                    seq_no=payload.seq_no,
                    snapshot_at=payload.snapshot_at,
                    positions=payload.positions,
                    exposures=payload.exposures,
                    metrics=payload.metrics,
                    raw_state=payload.raw_state,
                )
                writer._stamp(row)
                session.add(row)
                session.commit()
                return row.id
        except Exception:  # noqa: BLE001
            logger.exception("SnapshotWriter.write failed for bot %s", payload.bot_id)
            return None

    def latest(self) -> SnapshotPayload | None:
        """Return the most recent snapshot for this bot."""
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_bots import BotSnapshot
            from sqlalchemy import desc, select
        except Exception:  # noqa: BLE001
            return None
        try:
            with SessionLocal() as session:
                row = session.execute(
                    select(BotSnapshot)
                    .where(BotSnapshot.bot_id == self.bot_id)
                    .order_by(desc(BotSnapshot.seq_no))
                    .limit(1)
                ).scalar_one_or_none()
                if row is None:
                    return None
                return SnapshotPayload(
                    bot_id=row.bot_id,
                    seq_no=int(row.seq_no),
                    snapshot_at=row.snapshot_at,
                    run_id=row.run_id,
                    positions=dict(row.positions or {}),
                    exposures=dict(row.exposures or {}),
                    metrics=dict(row.metrics or {}),
                    raw_state=dict(row.raw_state or {}),
                )
        except Exception:  # noqa: BLE001
            return None


__all__ = ["SnapshotPayload", "SnapshotWriter"]
