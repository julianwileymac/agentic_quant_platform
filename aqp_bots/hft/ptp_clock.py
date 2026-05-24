"""PTP-disciplined wall clock (IEEE 1588).

HFT bots must satisfy Commission Delegated Regulation (EU) 2017/574
(RTS 25) — the timestamp granularity requirement is **exactly 1
microsecond** for "high frequency or algorithmic trading operations".
Reaching that requires the host clock to be PTP-disciplined via
``ptp4l`` + ``phc2sys`` from the ``linuxptp`` package.

This module:

1. Reads the PTP Hardware Clock (PHC) offset from ``phc2sys`` via its
   standard reporting interface (``/var/run/phc2sys.sock`` or stderr
   parsing).
2. Exposes :class:`PTPClock` which falls back to :class:`SystemClock`
   when no PHC is available so the rest of the code never crashes in
   non-PTP environments (CI, dev laptops).
3. Provides :func:`hardware_timestamps_available` so the operator's
   validating webhook can refuse HFT bot scheduling on nodes that
   don't have PHC sync.
"""
from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PTPStatus:
    """Snapshot of the PTP discipline state."""

    available: bool
    offset_ns: int | None = None
    last_sync_age_s: float | None = None
    notes: str = ""


def hardware_timestamps_available() -> bool:
    """Return True iff the kernel exposes at least one PHC device."""
    return any(Path("/dev").glob("ptp*"))


def query_phc2sys() -> PTPStatus:
    """Best-effort query of the current PTP offset via phc2sys.

    Returns :class:`PTPStatus` with ``available=False`` and a notes
    string when phc2sys isn't reachable (dev / CI / Windows). Production
    deployments should run phc2sys with ``-m -u 1`` and capture stderr
    into the standard journal so this query can be made via journalctl.

    For Phase 7 this is a placeholder; the production wire-up reads
    ``/var/run/phc2sys.sock`` (when phc2sys is configured to expose
    its status socket) or parses ``journalctl -u phc2sys`` for the
    latest ``offset`` value.
    """
    if not hardware_timestamps_available():
        return PTPStatus(available=False, notes="no /dev/ptp* devices")
    try:
        # Try ``pmc`` (the PTP management client) to query the local PHC.
        result = subprocess.run(
            ["pmc", "-u", "-b", "0", "GET CURRENT_DATA_SET"],
            capture_output=True,
            text=True,
            timeout=1.0,
        )
        if result.returncode != 0:
            return PTPStatus(
                available=False,
                notes=f"pmc exited {result.returncode}",
            )
        # Parse the master offset; pmc output looks like:
        #   masterOffsetFromSelf 123
        offset_ns = None
        for line in result.stdout.splitlines():
            if "masterOffset" in line:
                parts = line.strip().split()
                if len(parts) >= 2 and parts[-1].lstrip("-").isdigit():
                    offset_ns = int(parts[-1])
                    break
        return PTPStatus(
            available=offset_ns is not None,
            offset_ns=offset_ns,
            notes="phc2sys via pmc",
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return PTPStatus(available=False, notes="pmc not available")
    except Exception as exc:  # noqa: BLE001
        return PTPStatus(available=False, notes=f"pmc query failed: {exc!r}")


class PTPClock:
    """PTP-disciplined wall clock.

    Wraps :func:`time.clock_gettime(CLOCK_REALTIME)` (which is what
    ``phc2sys -s phc -O 0`` writes to) and exposes the same surface
    as :class:`aqp_bots.core.clock.SystemClock`. When PTP isn't
    available the class degrades silently to the system clock and the
    operator's validating webhook (Phase 8) rejects HFT bot
    scheduling on the node.
    """

    def __init__(self) -> None:
        self._status: PTPStatus = query_phc2sys()
        self._is_disciplined: bool = self._status.available

    @property
    def is_disciplined(self) -> bool:
        return self._is_disciplined

    @property
    def status(self) -> PTPStatus:
        return self._status

    def wall_time_ns(self) -> int:
        # CLOCK_REALTIME — the system clock disciplined by phc2sys
        # when it's running with ``-s <phc> -O 0``.
        return time.clock_gettime_ns(time.CLOCK_REALTIME) if hasattr(time, "clock_gettime_ns") else time.time_ns()

    def mono_time_ns(self) -> int:
        return time.monotonic_ns()

    def exchange_time_ns(self, venue: str) -> int:
        return self.wall_time_ns()


__all__ = [
    "PTPClock",
    "PTPStatus",
    "hardware_timestamps_available",
    "query_phc2sys",
]
