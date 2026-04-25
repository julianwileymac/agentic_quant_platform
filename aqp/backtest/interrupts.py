"""Backtest interrupt handlers — Phase-2 HITL pause/resume scaffolding.

The :class:`EventDrivenBacktester` accepts an optional
``interrupt_handler`` callback. When the engine produces an order that
matches a configured rule, it calls the handler synchronously with a
:class:`InterruptRequest` and uses the returned :class:`InterruptResolution`
to continue / skip / replace the order.

Two handler implementations live here:

- :class:`NullInterruptHandler` — never pauses; default for all
  existing callers so behaviour is unchanged unless interrupts are
  explicitly opted into.
- :class:`RedisInterruptHandler` — publishes the request on the WS
  broker (so a Next.js panel can render it), persists a
  :class:`BacktestInterrupt` row, then blocks on a Redis BLPOP key
  until the UI POSTs a response back.

The dataclass + interface live here so the engine module can stay
free of Redis / DB imports and remain easy to unit-test.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

logger = logging.getLogger(__name__)


InterruptAction = Literal["continue", "skip", "replace"]


@dataclass
class InterruptRequest:
    """Payload the engine hands to the interrupt handler."""

    backtest_id: str | None
    task_id: str | None
    timestamp: datetime
    rule: str
    bar_context: dict[str, Any] = field(default_factory=dict)
    pending_orders: list[dict[str, Any]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "backtest_id": self.backtest_id,
            "task_id": self.task_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "rule": self.rule,
            "bar_context": self.bar_context,
            "pending_orders": self.pending_orders,
            "extra": self.extra,
        }


@dataclass
class InterruptResolution:
    """Handler response that controls how the engine proceeds."""

    action: InterruptAction = "continue"
    replacement_orders: list[dict[str, Any]] = field(default_factory=list)
    note: str | None = None

    @classmethod
    def cont(cls) -> InterruptResolution:
        return cls(action="continue")

    @classmethod
    def skip(cls, note: str | None = None) -> InterruptResolution:
        return cls(action="skip", note=note)

    @classmethod
    def replace(
        cls,
        replacement_orders: list[dict[str, Any]],
        note: str | None = None,
    ) -> InterruptResolution:
        return cls(action="replace", replacement_orders=replacement_orders, note=note)


class InterruptHandler(Protocol):
    """Sync callback the engine invokes when an order matches a rule."""

    def __call__(self, request: InterruptRequest) -> InterruptResolution:
        ...


class NullInterruptHandler:
    """No-op handler — orders pass through unchanged."""

    def __call__(self, request: InterruptRequest) -> InterruptResolution:  # noqa: D401
        return InterruptResolution.cont()


# ---------------------------------------------------------------------------
# Rule matching helpers
# ---------------------------------------------------------------------------


def _coerce_number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def order_matches_rule(order: dict[str, Any], rule: dict[str, Any]) -> bool:
    """Return ``True`` when ``order`` triggers ``rule``.

    Rules are simple JSON dicts — the matcher recognises:

    - ``min_notional`` — order quantity * price >= threshold.
    - ``min_size_pct`` — sized as fraction of equity (already on the order).
    - ``max_confidence`` — agentic alpha confidence under threshold.
    - ``actions`` — list of order sides (``BUY|SELL``) that should pause.
    """
    actions = rule.get("actions")
    if actions:
        side = str(order.get("side") or order.get("direction") or "").upper()
        if side and side not in {a.upper() for a in actions}:
            return False
    min_notional = _coerce_number(rule.get("min_notional"))
    if min_notional is not None:
        qty = _coerce_number(order.get("quantity")) or 0.0
        price = _coerce_number(order.get("price")) or 0.0
        if qty * price < min_notional:
            return False
    min_size = _coerce_number(rule.get("min_size_pct"))
    if min_size is not None:
        if (_coerce_number(order.get("size_pct")) or 0.0) < min_size:
            return False
    max_conf = _coerce_number(rule.get("max_confidence"))
    if max_conf is not None:
        conf = _coerce_number(order.get("confidence"))
        if conf is None or conf > max_conf:
            return False
    return True


def find_first_matching_rule(
    orders: list[dict[str, Any]],
    rules: list[dict[str, Any]] | None,
) -> tuple[str, list[dict[str, Any]]] | None:
    """Return ``(rule_name, matched_orders)`` or ``None`` if nothing matched."""
    if not rules:
        return None
    for rule in rules:
        name = str(rule.get("name") or rule.get("rule") or "rule")
        matched = [o for o in orders if order_matches_rule(o, rule)]
        if matched:
            return name, matched
    return None


# ---------------------------------------------------------------------------
# Redis-backed handler
# ---------------------------------------------------------------------------


class RedisInterruptHandler:
    """Publish on the WS broker + block on a Redis list until the UI responds.

    Persists a :class:`aqp.persistence.models.BacktestInterrupt` row at
    request time so the UI can list pending interrupts even if the WS
    socket dropped, and updates it with the resolution payload after
    the BLPOP wakes up.
    """

    def __init__(
        self,
        backtest_id: str | None,
        task_id: str | None = None,
        *,
        timeout_seconds: float = 600.0,
        poll_seconds: float = 1.0,
    ) -> None:
        self.backtest_id = backtest_id
        self.task_id = task_id
        self.timeout_seconds = float(timeout_seconds)
        self.poll_seconds = max(0.05, float(poll_seconds))

    # ------------------------------------------------------------------ helpers --

    @staticmethod
    def _response_key(interrupt_id: str) -> str:
        return f"aqp:interrupt:{interrupt_id}:response"

    def _publish(self, payload: dict[str, Any]) -> None:
        try:
            from aqp.ws.broker import publish

            channel = self.task_id or self.backtest_id or "global"
            publish(channel, payload)
        except Exception:
            logger.exception("RedisInterruptHandler: publish failed")

    # --------------------------------------------------------------------- main --

    def __call__(self, request: InterruptRequest) -> InterruptResolution:
        interrupt_id = str(uuid.uuid4())
        resolution = InterruptResolution.cont()
        try:
            from aqp.persistence.db import get_session
            from aqp.persistence.models import BacktestInterrupt

            with get_session() as session:
                row = BacktestInterrupt(
                    id=interrupt_id,
                    backtest_id=self.backtest_id,
                    task_id=self.task_id,
                    ts=request.timestamp,
                    rule=request.rule,
                    status="pending",
                    payload=request.to_dict(),
                )
                session.add(row)
        except Exception:
            logger.exception("RedisInterruptHandler: could not persist interrupt row")

        self._publish(
            {
                "kind": "interrupt_pending",
                "interrupt_id": interrupt_id,
                "request": request.to_dict(),
            }
        )

        try:
            import redis

            from aqp.config import settings

            client = redis.Redis.from_url(
                settings.redis_pubsub_url, decode_responses=True
            )
            deadline = time.time() + self.timeout_seconds
            response_payload: dict[str, Any] | None = None
            while time.time() < deadline:
                raw = client.blpop(
                    self._response_key(interrupt_id), timeout=int(self.poll_seconds)
                )
                if raw is None:
                    continue
                try:
                    _, value = raw
                    response_payload = json.loads(value)
                except Exception:
                    response_payload = {"action": "continue"}
                break

            if response_payload is None:
                logger.warning(
                    "RedisInterruptHandler: timed out after %.1fs — continuing",
                    self.timeout_seconds,
                )
                self._mark_resolved(interrupt_id, status="expired")
                return InterruptResolution.cont()

            action = str(response_payload.get("action", "continue")).lower()
            if action == "skip":
                resolution = InterruptResolution.skip(
                    note=response_payload.get("note")
                )
            elif action == "replace":
                resolution = InterruptResolution.replace(
                    replacement_orders=list(
                        response_payload.get("replacement_orders") or []
                    ),
                    note=response_payload.get("note"),
                )
            else:
                resolution = InterruptResolution.cont()
            self._mark_resolved(interrupt_id, response=response_payload)
        except Exception:
            logger.exception("RedisInterruptHandler: BLPOP wait failed; continuing")
            self._mark_resolved(interrupt_id, status="error")
            return InterruptResolution.cont()

        self._publish(
            {
                "kind": "interrupt_resolved",
                "interrupt_id": interrupt_id,
                "action": resolution.action,
            }
        )
        return resolution

    def _mark_resolved(
        self,
        interrupt_id: str,
        *,
        status: str = "resolved",
        response: dict[str, Any] | None = None,
    ) -> None:
        try:
            from aqp.persistence.db import get_session
            from aqp.persistence.models import BacktestInterrupt

            with get_session() as session:
                row = session.get(BacktestInterrupt, interrupt_id)
                if row is None:
                    return
                row.status = status
                if response is not None:
                    row.response = response
                row.resolved_at = datetime.utcnow()
        except Exception:
            logger.debug(
                "RedisInterruptHandler: could not mark interrupt %s resolved",
                interrupt_id,
                exc_info=True,
            )


__all__ = [
    "InterruptAction",
    "InterruptHandler",
    "InterruptRequest",
    "InterruptResolution",
    "NullInterruptHandler",
    "RedisInterruptHandler",
    "find_first_matching_rule",
    "order_matches_rule",
]
