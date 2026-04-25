"""Clocks for the trading runtime.

Two implementations of :class:`aqp.core.interfaces.ITimeProvider`:

- :class:`RealTimeClock` — wall-clock for live/paper with an async sleep helper.
- :class:`SimulatedReplayClock` — deterministic, advanced one bar at a time
  during dry-runs and tests so fixture data is replayable.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from aqp.core.interfaces import ITimeProvider

_INTERVAL_SECONDS: dict[str, int] = {
    "1s": 1,
    "10s": 10,
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "1d": 86400,
}


def interval_seconds(interval: str) -> int:
    return _INTERVAL_SECONDS.get(interval, 60)


class RealTimeClock(ITimeProvider):
    """Timezone-aware UTC clock. Uses ``asyncio.sleep`` for non-blocking waits."""

    name = "real"

    def now(self) -> datetime:
        return datetime.now(tz=UTC)

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(max(0.0, seconds))

    async def sleep_until_next_bar(self, interval: str) -> None:
        seconds = interval_seconds(interval)
        now = self.now()
        next_tick = (now + timedelta(seconds=seconds)).replace(microsecond=0)
        delta = (next_tick - now).total_seconds()
        await self.sleep(max(0.0, delta))


class SimulatedReplayClock(ITimeProvider):
    """Clock advanced manually by the feed (used in dry-runs and tests)."""

    name = "sim"

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(1970, 1, 1, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def set_now(self, new_now: datetime) -> None:
        self._now = new_now

    async def sleep(self, seconds: float) -> None:
        self._now = self._now + timedelta(seconds=seconds)

    async def sleep_until_next_bar(self, interval: str) -> None:
        await self.sleep(interval_seconds(interval))
