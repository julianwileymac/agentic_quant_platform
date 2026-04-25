"""Thread-safe sync/async token-bucket rate limiter."""
from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from aqp.data.sources.alpha_vantage._errors import RateLimitError, RateLimitKind


@dataclass(frozen=True)
class RateLimiterSnapshot:
    rpm_limit: int
    daily_limit: int
    requests_this_minute: int
    requests_today: int
    tokens_available: float
    next_refill_seconds: float
    daily_reset_utc: str


class RateLimiter:
    """Token bucket with per-minute and optional UTC-day caps."""

    def __init__(self, rpm: int = 75, daily: int = 0, *, clock: Callable[[], float] | None = None) -> None:
        if rpm <= 0:
            raise ValueError("rpm must be positive")
        self.rpm = int(rpm)
        self.daily = max(int(daily), 0)
        self._clock = clock or time.monotonic
        self._wall_clock = time.time
        self._tokens = float(self.rpm)
        self._last_refill = self._clock()
        self._rolling_requests: list[float] = []
        self._daily_count = 0
        self._daily_window_start = self._wall_clock()
        self._lock = threading.Lock()
        self._async_lock = asyncio.Lock()

    def _refill_locked(self) -> None:
        now = self._clock()
        elapsed = now - self._last_refill
        if elapsed > 0:
            self._tokens = min(float(self.rpm), self._tokens + elapsed * (self.rpm / 60.0))
            self._last_refill = now
        cutoff = now - 60.0
        self._rolling_requests = [ts for ts in self._rolling_requests if ts > cutoff]

    def _rotate_daily_locked(self) -> None:
        now = self._wall_clock()
        now_utc = datetime.fromtimestamp(now, tz=timezone.utc)
        start_utc = datetime.fromtimestamp(self._daily_window_start, tz=timezone.utc)
        if now_utc.date() != start_utc.date():
            self._daily_count = 0
            self._daily_window_start = now

    def _next_token_locked(self) -> float:
        self._refill_locked()
        if self._tokens >= 1.0:
            return 0.0
        return (1.0 - self._tokens) * (60.0 / self.rpm)

    def _try_consume_locked(self) -> float | None:
        self._rotate_daily_locked()
        if self.daily and self._daily_count >= self.daily:
            raise RateLimitError(
                f"Alpha Vantage daily cap of {self.daily} requests reached; retry after UTC midnight.",
                kind=RateLimitKind.DAILY,
            )
        self._refill_locked()
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            self._rolling_requests.append(self._clock())
            self._daily_count += 1
            return None
        return self._next_token_locked()

    def acquire(self, *, timeout: float | None = None) -> None:
        deadline = None if timeout is None else self._clock() + timeout
        while True:
            with self._lock:
                wait = self._try_consume_locked()
            if wait is None:
                return
            if deadline is not None and self._clock() + wait > deadline:
                raise TimeoutError("Rate limiter timeout waiting for token")
            time.sleep(max(0.01, wait))

    async def aacquire(self, *, timeout: float | None = None) -> None:
        deadline = None if timeout is None else self._clock() + timeout
        while True:
            async with self._async_lock:
                with self._lock:
                    wait = self._try_consume_locked()
            if wait is None:
                return
            if deadline is not None and self._clock() + wait > deadline:
                raise TimeoutError("Rate limiter timeout waiting for token")
            await asyncio.sleep(max(0.01, wait))

    def snapshot(self) -> RateLimiterSnapshot:
        with self._lock:
            self._refill_locked()
            self._rotate_daily_locked()
            reset = datetime.fromtimestamp(self._daily_window_start, tz=timezone.utc)
            return RateLimiterSnapshot(
                rpm_limit=self.rpm,
                daily_limit=self.daily,
                requests_this_minute=len(self._rolling_requests),
                requests_today=self._daily_count,
                tokens_available=round(self._tokens, 3),
                next_refill_seconds=round(self._next_token_locked(), 3),
                daily_reset_utc=reset.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
            )


__all__ = ["RateLimiter", "RateLimiterSnapshot"]
