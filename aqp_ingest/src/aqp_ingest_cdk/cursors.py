"""Incremental sync cursor for survivorship-bias-free resumable backfills."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable


@dataclass(slots=True)
class PointInTimeIncrementalCursor:
    """Cursor that records the source's ``updated_at`` / ``filed_at``.

    Safe to resume from across worker restarts. The cursor field is
    persisted as an ISO-8601 string on the Airbyte state envelope;
    subclasses (Polygon, Databento, Alpaca, IEX) call
    :meth:`update` from inside ``stream_slices`` so the next sync
    picks up exactly where the previous one stopped.

    Survivorship-bias guarantee: the cursor monotonically tracks the
    SOURCE timestamp, never the wall-clock time at the worker. A
    backfill that processes 5-year-old data still resumes from
    where it stopped, not from today's date.
    """

    cursor_field: str
    state: dict[str, Any] = field(default_factory=dict)

    def latest(self, key: str) -> str | None:
        return self.state.get(key)

    def update(self, key: str, value: str | datetime) -> None:
        if isinstance(value, datetime):
            value = value.isoformat()
        existing = self.state.get(key)
        if existing is None or str(value) > str(existing):
            self.state[key] = str(value)

    def merge(self, other: dict[str, Any] | None) -> None:
        if not other:
            return
        for k, v in other.items():
            self.update(k, v)

    def to_state(self) -> dict[str, Any]:
        return dict(self.state)

    @classmethod
    def from_state(cls, cursor_field: str, raw: Any) -> PointInTimeIncrementalCursor:
        if raw is None:
            return cls(cursor_field=cursor_field, state={})
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = {}
        if not isinstance(raw, dict):
            raw = {}
        return cls(cursor_field=cursor_field, state=dict(raw))

    def iter_partitions(
        self,
        *,
        keys: Iterable[str],
        start: datetime,
        end: datetime,
        step_days: int = 1,
    ) -> Iterable[dict[str, str]]:
        """Yield day-by-day partitions resuming after the recorded cursor.

        Each slice carries ``{"key", "from", "to"}``; the connector
        uses ``key`` to disambiguate per-instrument cursors.
        """
        from datetime import timedelta

        for key in keys:
            latest_raw = self.latest(key)
            start_dt = start
            if latest_raw:
                try:
                    start_dt = max(start_dt, datetime.fromisoformat(latest_raw))
                except ValueError:
                    pass
            cur = start_dt
            while cur < end:
                nxt = min(end, cur + timedelta(days=step_days))
                yield {
                    "key": key,
                    "from": cur.date().isoformat(),
                    "to": nxt.date().isoformat(),
                }
                cur = nxt


__all__ = ["PointInTimeIncrementalCursor"]
