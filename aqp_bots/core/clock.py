"""Clock abstractions for the kernel runtime.

Four implementations:

- :class:`SystemClock` — ``time.time_ns`` / ``time.monotonic_ns`` (default
  for live trading).
- :class:`MonotonicClock` — monotonic-only (for measuring durations without
  wall-clock skew).
- :class:`SimulatedClock` — backtest / replay clock advanced by the
  historical-data adapter (the same code path runs live and in sim,
  preserving research-to-live parity per blueprint §A.4).
- :class:`PTPClock` — PTP-disciplined clock (IEEE 1588) wired through
  ``ptp4l`` + ``phc2sys``; mandatory for HFT bots that must satisfy the
  1-microsecond timestamp granularity required by Commission Delegated
  Regulation (EU) 2017/574 (RTS 25). Phase 7 module
  :mod:`aqp_bots.hft.ptp_clock` provides the concrete hardware backend.

All clocks expose three methods:

- ``wall_time_ns()`` — wall clock, ns since Unix epoch
- ``mono_time_ns()`` — monotonic, ns
- ``exchange_time_ns(venue)`` — venue-aware logical time (sim clocks
  advance only when the data feed advances)
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod


class Clock(ABC):
    """Abstract clock interface."""

    @abstractmethod
    def wall_time_ns(self) -> int:
        """Wall-clock nanoseconds since Unix epoch."""

    @abstractmethod
    def mono_time_ns(self) -> int:
        """Monotonic nanoseconds (epoch undefined; differences only)."""

    def exchange_time_ns(self, venue: str) -> int:
        """Venue-aware logical time. Default: wall clock.

        :class:`SimulatedClock` overrides this to advance only when the
        historical-data adapter releases the next event.
        """
        return self.wall_time_ns()


class SystemClock(Clock):
    """Real time. The default for live and paper trading."""

    def wall_time_ns(self) -> int:
        return time.time_ns()

    def mono_time_ns(self) -> int:
        return time.monotonic_ns()


class MonotonicClock(Clock):
    """Monotonic-only — wall calls fall back to mono."""

    def wall_time_ns(self) -> int:
        return time.monotonic_ns()

    def mono_time_ns(self) -> int:
        return time.monotonic_ns()


class SimulatedClock(Clock):
    """Backtest / replay clock.

    The historical-data adapter calls :meth:`advance` to push the clock
    forward; strategy code reads via :meth:`wall_time_ns` / :meth:`mono_time_ns`
    and sees the simulated time, preserving research-to-live parity.
    """

    def __init__(self, start_ns: int = 0) -> None:
        self._now_ns: int = int(start_ns)
        self._mono_origin_ns: int = int(start_ns)

    def advance(self, target_ns: int) -> None:
        """Advance the simulated clock. Must be monotonic."""
        target = int(target_ns)
        if target < self._now_ns:
            raise ValueError(
                f"Simulated clock cannot run backwards: now={self._now_ns} target={target}"
            )
        self._now_ns = target

    def wall_time_ns(self) -> int:
        return self._now_ns

    def mono_time_ns(self) -> int:
        return self._now_ns - self._mono_origin_ns


class PTPClock(SystemClock):
    """PTP-disciplined wall clock (placeholder).

    The full hardware backend lives in :mod:`aqp_bots.hft.ptp_clock` and
    reads the PHC offset from ``phc2sys``. This base class falls back to
    :class:`SystemClock` semantics when the PTP backend is unavailable so
    code that defaults to a PTP clock still runs in dev environments.
    """

    def __init__(self) -> None:
        self._ptp_available: bool = False
        try:
            from aqp_bots.hft import ptp_clock  # noqa: F401

            self._ptp_available = True
        except Exception:  # noqa: BLE001
            self._ptp_available = False

    def is_disciplined(self) -> bool:
        """Return True iff a PTP hardware backend is active."""
        return self._ptp_available


_DEFAULT_CLOCK: Clock | None = None


def get_default_clock() -> Clock:
    """Return the process-wide default clock (lazy-built)."""
    global _DEFAULT_CLOCK
    if _DEFAULT_CLOCK is None:
        _DEFAULT_CLOCK = SystemClock()
    return _DEFAULT_CLOCK


def set_default_clock(clock: Clock) -> None:
    """Override the default clock (used by backtest / test fixtures)."""
    global _DEFAULT_CLOCK
    _DEFAULT_CLOCK = clock


__all__ = [
    "Clock",
    "MonotonicClock",
    "PTPClock",
    "SimulatedClock",
    "SystemClock",
    "get_default_clock",
    "set_default_clock",
]
