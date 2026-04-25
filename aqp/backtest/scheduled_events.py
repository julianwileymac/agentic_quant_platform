"""Scheduled events (Lean ``ScheduledEventManager``).

Provides a small cron-like scheduler that strategies can use to request
callbacks at market open, market close, or specific weekdays.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any


@dataclass
class ScheduledEvent:
    name: str
    callback: Callable[[datetime], Any]
    at: str = "market_open"  # market_open | market_close | weekly | monthly | daily
    weekday: int | None = None  # for weekly (0=Mon)
    day_of_month: int | None = None  # for monthly
    local_time: time | None = None


class ScheduledEventManager:
    """Fires registered callbacks when the replay clock crosses their trigger."""

    def __init__(self) -> None:
        self._events: list[ScheduledEvent] = []
        self._last_fire: dict[str, datetime] = {}

    def register(self, event: ScheduledEvent) -> None:
        self._events.append(event)

    def clear(self) -> None:
        self._events.clear()
        self._last_fire.clear()

    def tick(self, ts: datetime) -> list[str]:
        """Advance the clock; invoke callbacks whose trigger matches ``ts``.

        Returns the list of event names fired on this tick.
        """
        fired: list[str] = []
        for event in self._events:
            if self._should_fire(event, ts):
                last = self._last_fire.get(event.name)
                if last and last.date() == ts.date() and event.at != "daily":
                    continue
                try:
                    event.callback(ts)
                except Exception:
                    continue
                self._last_fire[event.name] = ts
                fired.append(event.name)
        return fired

    def _should_fire(self, event: ScheduledEvent, ts: datetime) -> bool:
        if event.at == "daily":
            return True
        if event.at == "weekly":
            if event.weekday is None:
                return False
            return ts.weekday() == event.weekday
        if event.at == "monthly":
            if event.day_of_month is None:
                return False
            return ts.day == event.day_of_month
        if event.at == "market_open":
            return ts.hour == 9 and ts.minute >= 30
        if event.at == "market_close":
            return ts.hour == 16
        if event.at == "specific_time" and event.local_time:
            return ts.time().replace(second=0, microsecond=0) == event.local_time
        return False
