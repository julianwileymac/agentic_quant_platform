"""Pre-trade risk policies (RTS 6 Art. 15 + SEC 15c3-5 (c)(1)).

Every policy implements the :class:`PreTradePolicy` Protocol. The
:class:`PreTradeRiskEngine` composes a list of policies and runs them
on each :class:`NewOrder` before the kernel forwards it to the
execution adapter.

Each policy returns a :class:`PolicyVerdict` with one of three
severities — ``allow``, ``warn``, ``block`` — plus a regulatory
citation so the validation report (Art. 9) can attribute every
rejection to a named control.

Hard / soft block discrimination (ESMA Supervisory Briefing §72/§75):

- ``severity == "block"`` is a *hard block*: the order MUST NOT leave
  the bot. The policy mapping to RTS 6 Art. 15(1)(a)-(d) hard limits
  are hard blocks.
- ``severity == "warn"`` is a *soft block*: the policy maps to ESMA §75
  "soft" thresholds and is informational only; operator may override
  via :attr:`PolicyVerdict.allow_override`.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable, Literal, Protocol, runtime_checkable

from aqp_bots.schemas.trading import NewOrder

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PolicyVerdict:
    """Outcome of one policy evaluation."""

    policy: str
    severity: Literal["allow", "warn", "block"]
    reason: str = ""
    citation: str = ""  # e.g. "RTS 6 Art. 15(1)(a)"
    allow_override: bool = False
    extras: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class PreTradeContext:
    """Snapshot the engine passes to each policy.

    Lightweight (msgspec-friendly) — distinct from
    :class:`aqp.risk.manager.PreTradeContext` which carries a richer
    equity/positions snapshot for the legacy paper-trading path.
    """

    mark_price: Decimal | None = None
    bid_price: Decimal | None = None
    ask_price: Decimal | None = None
    realized_vol_5min: float | None = None
    equity_usd: Decimal | None = None
    cash_usd: Decimal | None = None
    open_positions: int = 0


@runtime_checkable
class PreTradePolicy(Protocol):
    """Protocol every pre-trade policy implements."""

    name: str
    citation: str

    def evaluate(self, order: NewOrder, ctx: PreTradeContext) -> PolicyVerdict:
        ...


# ---------------------------------------------------------------------------
# RTS 6 Art. 15(1)(a) — price collars
# ---------------------------------------------------------------------------


class PriceCollarPolicy:
    """RTS 6 Art. 15(1)(a) / 15c3-5 (c)(1)(i) — reject orders outside a
    collar around the reference price.

    The "reference price" is, in order of preference:
    1. The midpoint of the current quote, if available.
    2. The last trade price, if available.
    3. The order's own ``limit_price`` (degenerate — policy passes).
    """

    name = "price_collar"
    citation = "RTS 6 Art. 15(1)(a) / SEC 15c3-5 (c)(1)(i)"

    def __init__(self, *, max_bps: int) -> None:
        if max_bps <= 0:
            raise ValueError("max_bps must be > 0")
        self.max_bps = max_bps

    def evaluate(self, order: NewOrder, ctx: PreTradeContext) -> PolicyVerdict:
        if order.limit_price is None:
            return PolicyVerdict(self.name, "allow", citation=self.citation)
        ref = ctx.mark_price
        if ref is None and ctx.bid_price and ctx.ask_price:
            ref = (ctx.bid_price + ctx.ask_price) / Decimal(2)
        if ref is None or ref <= 0:
            return PolicyVerdict(self.name, "allow", citation=self.citation)
        diff_bps = abs(order.limit_price - ref) / ref * Decimal(10000)
        if diff_bps > Decimal(self.max_bps):
            return PolicyVerdict(
                self.name,
                "block",
                reason=(
                    f"limit_price={order.limit_price} {diff_bps:.0f}bps from ref={ref}; "
                    f"max={self.max_bps}bps"
                ),
                citation=self.citation,
            )
        return PolicyVerdict(self.name, "allow", citation=self.citation)


# ---------------------------------------------------------------------------
# RTS 6 Art. 15(1)(b) — maximum order value
# ---------------------------------------------------------------------------


class MaxOrderValuePolicy:
    """RTS 6 Art. 15(1)(b) / 15c3-5 (c)(1)(i) — cap notional per order."""

    name = "max_order_value"
    citation = "RTS 6 Art. 15(1)(b) / SEC 15c3-5 (c)(1)(i)"

    def __init__(self, *, max_value_usd: Decimal) -> None:
        if max_value_usd <= 0:
            raise ValueError("max_value_usd must be > 0")
        self.max_value_usd = max_value_usd

    def evaluate(self, order: NewOrder, ctx: PreTradeContext) -> PolicyVerdict:
        price = order.limit_price or ctx.mark_price
        if price is None:
            return PolicyVerdict(self.name, "warn", reason="no ref price; admitting", citation=self.citation)
        notional = price * order.quantity
        if notional > self.max_value_usd:
            return PolicyVerdict(
                self.name,
                "block",
                reason=f"notional={notional} > cap={self.max_value_usd}",
                citation=self.citation,
            )
        return PolicyVerdict(self.name, "allow", citation=self.citation)


# ---------------------------------------------------------------------------
# RTS 6 Art. 15(1)(c) — maximum order volume
# ---------------------------------------------------------------------------


class MaxOrderVolumePolicy:
    """RTS 6 Art. 15(1)(c) / 15c3-5 (c)(1)(i) — cap quantity per order."""

    name = "max_order_volume"
    citation = "RTS 6 Art. 15(1)(c) / SEC 15c3-5 (c)(1)(i)"

    def __init__(self, *, max_qty: Decimal) -> None:
        if max_qty <= 0:
            raise ValueError("max_qty must be > 0")
        self.max_qty = max_qty

    def evaluate(self, order: NewOrder, ctx: PreTradeContext) -> PolicyVerdict:
        if order.quantity > self.max_qty:
            return PolicyVerdict(
                self.name,
                "block",
                reason=f"qty={order.quantity} > cap={self.max_qty}",
                citation=self.citation,
            )
        return PolicyVerdict(self.name, "allow", citation=self.citation)


# ---------------------------------------------------------------------------
# RTS 6 Art. 15(1)(d) — maximum messages limit
# ---------------------------------------------------------------------------


class MaxMessagesPerSecondPolicy:
    """RTS 6 Art. 15(1)(d) — cap outbound order message rate.

    Uses a rolling 1-second window of submission timestamps.
    """

    name = "max_messages_per_second"
    citation = "RTS 6 Art. 15(1)(d)"

    def __init__(self, *, max_rate: int) -> None:
        if max_rate <= 0:
            raise ValueError("max_rate must be > 0")
        self.max_rate = max_rate
        self._window: deque[float] = deque()

    def evaluate(self, order: NewOrder, ctx: PreTradeContext) -> PolicyVerdict:
        now = time.monotonic()
        # Evict everything older than 1 second.
        while self._window and self._window[0] < now - 1.0:
            self._window.popleft()
        if len(self._window) + 1 > self.max_rate:
            return PolicyVerdict(
                self.name,
                "block",
                reason=f"rate {len(self._window) + 1}/s > cap {self.max_rate}/s",
                citation=self.citation,
            )
        self._window.append(now)
        return PolicyVerdict(self.name, "allow", citation=self.citation)


# ---------------------------------------------------------------------------
# RTS 6 Art. 15(3) — repeated-execution throttle
# ---------------------------------------------------------------------------


class RepeatedExecutionThrottlePolicy:
    """RTS 6 Art. 15(3) — throttle repeated execution of the same algorithm.

    Tracks the last submission per ``(strategy_id, symbol)`` and blocks
    submissions within ``min_interval_ms`` of the previous one.
    """

    name = "repeated_execution_throttle"
    citation = "RTS 6 Art. 15(3)"

    def __init__(self, *, min_interval_ms: int) -> None:
        if min_interval_ms < 0:
            raise ValueError("min_interval_ms must be >= 0")
        self.min_interval_ms = min_interval_ms
        self._last: dict[tuple[str, str], float] = {}

    def evaluate(self, order: NewOrder, ctx: PreTradeContext) -> PolicyVerdict:
        key = (order.strategy_id or "", order.symbol)
        now_ms = time.monotonic() * 1000.0
        last = self._last.get(key)
        if last is not None and now_ms - last < self.min_interval_ms:
            return PolicyVerdict(
                self.name,
                "block",
                reason=(
                    f"repeated execution: {now_ms - last:.0f}ms since last "
                    f"(min {self.min_interval_ms}ms)"
                ),
                citation=self.citation,
            )
        self._last[key] = now_ms
        return PolicyVerdict(self.name, "allow", citation=self.citation)


# ---------------------------------------------------------------------------
# RTS 6 Art. 15(5) — permission to trade instrument
# ---------------------------------------------------------------------------


class InstrumentAllowlistPolicy:
    """RTS 6 Art. 15(5) / 15c3-5 (c)(1)(ii) — limit instruments traded.

    Accepts the order only if ``order.symbol`` is in the configured
    allowlist.
    """

    name = "instrument_allowlist"
    citation = "RTS 6 Art. 15(5) / SEC 15c3-5 (c)(1)(ii)"

    def __init__(self, *, allowlist: Iterable[str]) -> None:
        self.allowlist = frozenset(allowlist)

    def evaluate(self, order: NewOrder, ctx: PreTradeContext) -> PolicyVerdict:
        if not self.allowlist:
            return PolicyVerdict(self.name, "allow", citation=self.citation)
        if order.symbol not in self.allowlist:
            return PolicyVerdict(
                self.name,
                "block",
                reason=f"symbol {order.symbol} not in allowlist",
                citation=self.citation,
            )
        return PolicyVerdict(self.name, "allow", citation=self.citation)


# ---------------------------------------------------------------------------
# Supplemental policies (not strict RTS 6 mappings but standard practice)
# ---------------------------------------------------------------------------


class BuyingPowerPolicy:
    """Reject orders that exceed available buying power."""

    name = "buying_power"
    citation = "SEC 15c3-5 (c)(1)(i) [capital]"

    def __init__(self, *, leverage: Decimal = Decimal("1")) -> None:
        self.leverage = leverage

    def evaluate(self, order: NewOrder, ctx: PreTradeContext) -> PolicyVerdict:
        if ctx.cash_usd is None or ctx.equity_usd is None:
            return PolicyVerdict(self.name, "warn", reason="no account context", citation=self.citation)
        price = order.limit_price or ctx.mark_price
        if price is None:
            return PolicyVerdict(self.name, "warn", reason="no ref price", citation=self.citation)
        notional = order.quantity * price
        max_bp = ctx.cash_usd + (ctx.equity_usd - ctx.cash_usd) * self.leverage
        if notional > max_bp:
            return PolicyVerdict(
                self.name,
                "block",
                reason=f"notional={notional} > buying_power={max_bp}",
                citation=self.citation,
            )
        return PolicyVerdict(self.name, "allow", citation=self.citation)


class FatFingerPolicy:
    """Block grossly oversized orders (multi-sigma above recent typical)."""

    name = "fat_finger"
    citation = "ESMA RTS 6 §63 (operator-defined)"

    def __init__(self, *, typical_size: Decimal, multiplier: float = 10.0) -> None:
        self.typical_size = typical_size
        self.multiplier = multiplier

    def evaluate(self, order: NewOrder, ctx: PreTradeContext) -> PolicyVerdict:
        threshold = self.typical_size * Decimal(str(self.multiplier))
        if order.quantity > threshold:
            return PolicyVerdict(
                self.name,
                "block",
                reason=f"qty={order.quantity} > {self.multiplier}x typical ({threshold})",
                citation=self.citation,
                allow_override=True,
            )
        return PolicyVerdict(self.name, "allow", citation=self.citation)


class VolatilityCircuitBreakerPolicy:
    """Halt new orders when realized volatility exceeds threshold."""

    name = "volatility_circuit_breaker"
    citation = "ESMA RTS 6 §66 (volatility limits)"

    def __init__(self, *, max_realized_vol: float) -> None:
        self.max_realized_vol = max_realized_vol

    def evaluate(self, order: NewOrder, ctx: PreTradeContext) -> PolicyVerdict:
        if ctx.realized_vol_5min is None:
            return PolicyVerdict(self.name, "allow", citation=self.citation)
        if ctx.realized_vol_5min > self.max_realized_vol:
            return PolicyVerdict(
                self.name,
                "block",
                reason=(
                    f"realized vol {ctx.realized_vol_5min:.4f} > "
                    f"cap {self.max_realized_vol:.4f}"
                ),
                citation=self.citation,
            )
        return PolicyVerdict(self.name, "allow", citation=self.citation)


__all__ = [
    "BuyingPowerPolicy",
    "FatFingerPolicy",
    "InstrumentAllowlistPolicy",
    "MaxMessagesPerSecondPolicy",
    "MaxOrderValuePolicy",
    "MaxOrderVolumePolicy",
    "PolicyVerdict",
    "PreTradeContext",
    "PreTradePolicy",
    "PriceCollarPolicy",
    "RepeatedExecutionThrottlePolicy",
    "VolatilityCircuitBreakerPolicy",
]
