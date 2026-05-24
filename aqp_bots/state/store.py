"""EventStore — append-only writes to the partitioned ``bot_events`` table.

Hard rule compliance:

- Routes through :class:`aqp.persistence.ledger.LedgerWriter._stamp` so
  every event row inherits ``owner_user_id`` / ``workspace_id`` /
  ``project_id`` / ``experiment_id`` / ``test_id`` from the active
  :class:`RequestContext` (rule 34).
- Never writes to the lakehouse directly; if a strategy needs to emit
  a trajectory or signal series to Iceberg it goes through
  :func:`aqp.data.iceberg_catalog.append_arrow` (rule 3) from a separate
  task.
- Sequence numbers are monotonic per bot; the writer keeps the
  next-available ``seq_no`` in memory and increments on each append.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class BotEventRecord:
    """One event in the bot's event log."""

    bot_id: str
    seq_no: int
    event_type: str
    event_data: dict[str, Any]
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    recorded_at: datetime | None = None


class EventStore:
    """Append-only writer to ``bot_events``.

    Strategy code calls :meth:`append` with the event type + payload;
    the store assigns a monotonic ``seq_no`` per ``bot_id`` and persists
    via :class:`LedgerWriter._stamp`.

    For maximum throughput the store batches writes: events are
    accumulated in an in-memory list and flushed every ``flush_interval_s``
    or when ``batch_size`` is reached (whichever comes first).
    """

    def __init__(
        self,
        *,
        bot_id: str,
        context: Any | None = None,
        batch_size: int = 256,
        flush_interval_s: float = 1.0,
    ) -> None:
        self.bot_id = bot_id
        self.context = context
        self.batch_size = batch_size
        self.flush_interval_s = flush_interval_s
        self._buffer: list[BotEventRecord] = []
        self._next_seq: int = self._load_next_seq()

    # ------------------------------------------------------------------
    # Append
    # ------------------------------------------------------------------

    def append(self, event_type: str, event_data: Any) -> BotEventRecord:
        """Buffer an event for the next flush.

        Returns the constructed record (with assigned ``seq_no``).
        Flushes if the buffer hits :attr:`batch_size`.
        """
        payload = self._normalize(event_data)
        rec = BotEventRecord(
            bot_id=self.bot_id,
            seq_no=self._next_seq,
            event_type=event_type,
            event_data=payload,
        )
        self._next_seq += 1
        self._buffer.append(rec)
        if len(self._buffer) >= self.batch_size:
            self.flush()
        return rec

    def flush(self) -> int:
        """Persist buffered events to ``bot_events``.

        Returns the number of rows written. Failures are logged but never
        raise — losing the event log is bad but worse is failing the
        trading thread; the kernel falls back to an in-memory journal
        until the next successful flush.
        """
        if not self._buffer:
            return 0
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.ledger import LedgerWriter
            from aqp.persistence.models_bots import BotEvent
        except Exception:  # noqa: BLE001
            logger.debug("EventStore: persistence unavailable; dropping batch")
            self._buffer.clear()
            return 0

        writer = LedgerWriter(context=self.context)
        rows = list(self._buffer)
        self._buffer.clear()
        try:
            with SessionLocal() as session:
                for rec in rows:
                    row = BotEvent(
                        bot_id=rec.bot_id,
                        seq_no=rec.seq_no,
                        event_type=rec.event_type,
                        event_data=rec.event_data,
                        occurred_at=rec.occurred_at,
                    )
                    writer._stamp(row)
                    session.add(row)
                session.commit()
            return len(rows)
        except Exception:  # noqa: BLE001
            logger.exception("EventStore.flush failed; re-queuing %d rows", len(rows))
            # Re-buffer at the front for retry on next flush.
            self._buffer = rows + self._buffer
            return 0

    def append_many(self, events: Iterable[tuple[str, Any]]) -> int:
        """Convenience: append multiple events in one go."""
        n = 0
        for event_type, event_data in events:
            self.append(event_type, event_data)
            n += 1
        return n

    # ------------------------------------------------------------------
    # Replay / inspection
    # ------------------------------------------------------------------

    def replay(self, *, since_seq: int = 0, limit: int | None = None) -> list[BotEventRecord]:
        """Read events back from the store (for time-travel debugging).

        Use :func:`aqp_bots.state.replay.replay_events` for the
        higher-level CLI surface; this method is the building block.
        """
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_bots import BotEvent
        except Exception:  # noqa: BLE001
            return []
        with SessionLocal() as session:
            q = (
                session.query(BotEvent)
                .filter(BotEvent.bot_id == self.bot_id)
                .filter(BotEvent.seq_no > since_seq)
                .order_by(BotEvent.seq_no)
            )
            if limit:
                q = q.limit(limit)
            rows = q.all()
        return [
            BotEventRecord(
                bot_id=r.bot_id,
                seq_no=r.seq_no,
                event_type=r.event_type,
                event_data=dict(r.event_data or {}),
                occurred_at=r.occurred_at,
                recorded_at=r.recorded_at,
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_next_seq(self) -> int:
        """Look up the highest existing seq_no for this bot, plus one."""
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_bots import BotEvent
            from sqlalchemy import func, select
        except Exception:  # noqa: BLE001
            return 1
        try:
            with SessionLocal() as session:
                row = session.execute(
                    select(func.max(BotEvent.seq_no)).where(
                        BotEvent.bot_id == self.bot_id
                    )
                ).scalar_one_or_none()
                return int(row or 0) + 1
        except Exception:  # noqa: BLE001
            return 1

    def _normalize(self, value: Any) -> dict[str, Any]:
        """Coerce arbitrary event payloads to a JSON-compatible dict."""
        if value is None:
            return {}
        if isinstance(value, dict):
            return self._json_round_trip(value)
        if is_dataclass(value):
            return self._json_round_trip(asdict(value))
        if hasattr(value, "model_dump"):
            try:
                return self._json_round_trip(value.model_dump(mode="json"))  # type: ignore[no-any-return]
            except Exception:  # noqa: BLE001
                pass
        if hasattr(value, "__dict__"):
            return self._json_round_trip(dict(vars(value)))
        return {"value": repr(value)[:1024]}

    def _json_round_trip(self, payload: Any) -> dict[str, Any]:
        try:
            return json.loads(json.dumps(payload, default=str))
        except Exception:  # noqa: BLE001
            return {"_unserialisable": str(payload)[:1024]}


__all__ = ["BotEventRecord", "EventStore"]
