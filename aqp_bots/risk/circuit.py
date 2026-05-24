"""Circuit breaker with hysteresis and cool-down.

Used by the risk engine when a non-RTS-6 condition (e.g. excessive
reject rate, latency spike, p&l drawdown) needs to halt new submissions
temporarily without engaging a full kill switch.

Three states:

- ``closed`` — traffic flows normally.
- ``open`` — traffic is blocked; will stay open for at least ``cool_down_s``.
- ``half_open`` — probe state; allows a single trial submission;
  success returns to ``closed``, failure returns to ``open``.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger(__name__)


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(slots=True)
class CircuitBreaker:
    """Standard 3-state circuit breaker.

    Construction parameters:
    - ``failure_threshold`` — consecutive failures to trip
    - ``cool_down_s`` — minimum time the breaker stays OPEN
    - ``recovery_threshold`` — successful probes in HALF_OPEN to close
    """

    failure_threshold: int = 5
    cool_down_s: float = 30.0
    recovery_threshold: int = 1
    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_state_change: float = 0.0

    def on_success(self) -> None:
        self.consecutive_failures = 0
        if self.state == CircuitState.HALF_OPEN:
            self.consecutive_successes += 1
            if self.consecutive_successes >= self.recovery_threshold:
                self._transition(CircuitState.CLOSED)

    def on_failure(self) -> None:
        self.consecutive_successes = 0
        self.consecutive_failures += 1
        if self.state == CircuitState.CLOSED:
            if self.consecutive_failures >= self.failure_threshold:
                self._transition(CircuitState.OPEN)
        elif self.state == CircuitState.HALF_OPEN:
            self._transition(CircuitState.OPEN)

    def allow_request(self) -> bool:
        """Test whether a request may proceed."""
        now = time.monotonic()
        if self.state == CircuitState.OPEN:
            if now - self.last_state_change >= self.cool_down_s:
                self._transition(CircuitState.HALF_OPEN)
                return True  # one probe
            return False
        return True  # closed or half_open (probing)

    def _transition(self, new_state: CircuitState) -> None:
        if new_state == self.state:
            return
        logger.info("circuit breaker %s -> %s", self.state.value, new_state.value)
        self.state = new_state
        self.consecutive_failures = 0
        self.consecutive_successes = 0
        self.last_state_change = time.monotonic()


__all__ = ["CircuitBreaker", "CircuitState"]
