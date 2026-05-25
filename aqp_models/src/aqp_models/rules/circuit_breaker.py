"""CircuitBreaker — rolling failure-window guard.

The breaker counts ``rule_name='circuit_breaker'`` rejections per skill
over a configurable rolling window. When the count exceeds
``max_failures`` the breaker trips and subsequent invocations are
rejected without running any downstream interface. The breaker
re-arms once the window expires.

The breaker also writes one row to ``ml_ood_violations`` per
rejection so the agent / operator can audit why traffic stopped.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any

from aqp_models.rules.base import MLRule, RuleVerdict

logger = logging.getLogger(__name__)


class CircuitBreaker(MLRule):
    """Rolling-window failure tracker."""

    rule_name = "circuit_breaker"
    rule_tags = ("safety",)
    severity = "block"

    def __init__(
        self,
        *,
        max_failures: int = 5,
        window_seconds: float = 60.0,
    ) -> None:
        self.max_failures = int(max_failures)
        self.window_seconds = float(window_seconds)
        self._lock = threading.RLock()
        self._failures: dict[str, deque[float]] = {}

    def evaluate(
        self,
        *,
        payload: dict[str, Any],
        step: Any | None = None,
        ctx: Any | None = None,
    ) -> RuleVerdict:
        key = self._key(step)
        now = time.monotonic()
        with self._lock:
            bucket = self._failures.setdefault(key, deque())
            # Evict expired entries.
            cutoff = now - self.window_seconds
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_failures:
                self._record_violation(
                    ctx=ctx,
                    step=step,
                    n=len(bucket),
                    reason="breaker_tripped",
                )
                return RuleVerdict(
                    allowed=False,
                    reason=(
                        f"circuit breaker tripped for {key!r}: "
                        f"{len(bucket)} failures in last {self.window_seconds:.0f}s"
                    ),
                    metadata={
                        "failures_in_window": len(bucket),
                        "window_seconds": self.window_seconds,
                        "max_failures": self.max_failures,
                    },
                )

        # If the upstream payload reports a prior failure, register it.
        last_error = (payload or {}).get("_last_error")
        if last_error:
            with self._lock:
                self._failures.setdefault(key, deque()).append(now)
            self._record_violation(
                ctx=ctx,
                step=step,
                n=len(self._failures[key]),
                reason="upstream_failure",
            )
        return RuleVerdict(allowed=True, reason="breaker armed")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _key(self, step: Any | None) -> str:
        if step is None:
            return "__global__"
        return getattr(step, "name", None) or step.__class__.__name__

    def _record_violation(
        self,
        *,
        ctx: Any | None,
        step: Any | None,
        n: int,
        reason: str,
    ) -> None:
        try:
            from datetime import datetime

            from aqp.persistence.db import get_session
            from aqp.persistence.models_mlops import MlOodViolation

            with get_session() as session:
                workspace_id = getattr(ctx, "workspace_id", None) if ctx else None
                project_id = getattr(ctx, "project_id", None) if ctx else None
                step_name = getattr(step, "name", None) if step else None
                row = MlOodViolation(
                    rule_name=self.rule_name,
                    skill_step=step_name,
                    reason=reason,
                    failures_in_window=int(n),
                    workspace_id=workspace_id,
                    project_id=project_id,
                    occurred_at=datetime.utcnow(),
                )
                session.add(row)
        except Exception:  # noqa: BLE001
            logger.debug("ood violation persist failed", exc_info=True)


__all__ = ["CircuitBreaker"]
