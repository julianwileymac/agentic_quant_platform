"""Pre-trade risk engine.

Composes a list of :class:`PreTradePolicy` instances and runs them on
each :class:`NewOrder` before it reaches the execution adapter. Extends
the existing :class:`aqp.risk.manager.RiskManager` layer-1 path (the
7 baseline checks: kill switch, daily loss, drawdown, position pct,
gross exposure, concentration, buying power) with the additional RTS 6
Article 15(1) and SEC 15c3-5 (c)(1) checks.

Hard rule: this engine sits behind :class:`BotRuntime` (rule 14). The
kernel's ``risk_task`` coroutine consumes ``NewOrder`` from the bus,
runs the engine, and only forwards passing orders to the execution
adapter — strategies never bypass this gate.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable

from aqp_bots.risk.kill_switch_v2 import is_engaged_scoped
from aqp_bots.risk.policies import (
    PolicyVerdict,
    PreTradeContext,
    PreTradePolicy,
)
from aqp_bots.schemas.trading import NewOrder

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PreTradeVerdict:
    """Aggregate result of running all policies on one order."""

    order: NewOrder
    passed: bool
    severity: str = "allow"  # worst severity across all policies
    verdicts: list[PolicyVerdict] = field(default_factory=list)

    @property
    def block_reasons(self) -> list[str]:
        return [v.reason for v in self.verdicts if v.severity == "block"]

    @property
    def citations(self) -> list[str]:
        return [v.citation for v in self.verdicts if v.severity == "block"]


class PreTradeRiskEngine:
    """In-bot Layer-1 pre-trade engine.

    Usage::

        engine = PreTradeRiskEngine(policies=[
            PriceCollarPolicy(max_bps=50),
            MaxOrderValuePolicy(max_value_usd=Decimal("250000")),
            MaxOrderVolumePolicy(max_qty=Decimal("10000")),
            MaxMessagesPerSecondPolicy(max_rate=50),
        ])
        verdict = engine.evaluate(order, ctx)
        if not verdict.passed:
            log_and_drop(verdict)
        else:
            await execution_adapter.place(order)
    """

    def __init__(
        self,
        *,
        policies: Iterable[PreTradePolicy] = (),
        bot_id: str | None = None,
        fleet_id: str | None = None,
        check_kill_switch: bool = True,
        check_legacy_risk_manager: bool = True,
    ) -> None:
        self.policies: list[PreTradePolicy] = list(policies)
        self.bot_id = bot_id
        self.fleet_id = fleet_id
        self.check_kill_switch = check_kill_switch
        self.check_legacy_risk_manager = check_legacy_risk_manager

    def add_policy(self, policy: PreTradePolicy) -> None:
        self.policies.append(policy)

    def evaluate(self, order: NewOrder, ctx: PreTradeContext | None = None) -> PreTradeVerdict:
        ctx = ctx or PreTradeContext()
        verdicts: list[PolicyVerdict] = []

        # --- 1. Kill switch (highest priority) ---------------------------
        if self.check_kill_switch:
            killed_reason = self._kill_switch_reason()
            if killed_reason:
                v = PolicyVerdict(
                    policy="kill_switch_v2",
                    severity="block",
                    reason=f"kill switch engaged ({killed_reason})",
                    citation="RTS 6 Art. 12 (kill functionality)",
                )
                return PreTradeVerdict(order=order, passed=False, severity="block", verdicts=[v])

        # --- 2. Legacy risk manager (delegate to existing) ---------------
        if self.check_legacy_risk_manager:
            legacy_verdict = self._run_legacy_risk_manager(order, ctx)
            if legacy_verdict is not None:
                verdicts.append(legacy_verdict)
                if legacy_verdict.severity == "block":
                    return PreTradeVerdict(
                        order=order,
                        passed=False,
                        severity="block",
                        verdicts=verdicts,
                    )

        # --- 3. RTS 6 / 15c3-5 policies ----------------------------------
        for policy in self.policies:
            try:
                v = policy.evaluate(order, ctx)
            except Exception as exc:  # noqa: BLE001
                logger.exception("policy %s raised", policy.name)
                v = PolicyVerdict(
                    policy=policy.name,
                    severity="block",
                    reason=f"policy exception: {exc!r}",
                    citation=policy.citation,
                )
            verdicts.append(v)
            if v.severity == "block" and not v.allow_override:
                # Stop on first hard block — fail fast.
                return PreTradeVerdict(
                    order=order, passed=False, severity="block", verdicts=verdicts
                )

        worst = _worst_severity(verdicts)
        passed = worst != "block"
        return PreTradeVerdict(
            order=order, passed=passed, severity=worst, verdicts=verdicts
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _kill_switch_reason(self) -> str | None:
        """Return the engagement reason or None."""
        # Platform first (most severe), then fleet, then bot.
        for scope, key in (
            ("platform", "platform"),
            ("fleet", self.fleet_id or "_none_"),
            ("bot", self.bot_id or "_none_"),
        ):
            engaged = is_engaged_scoped(scope, key)
            if engaged:
                return f"{scope}:{key}"
        # Backwards compat — the legacy global key.
        try:
            from aqp.risk.kill_switch import is_engaged as _legacy_engaged

            if _legacy_engaged():
                return "legacy_global"
        except Exception:  # noqa: BLE001
            pass
        return None

    def _run_legacy_risk_manager(
        self, order: NewOrder, ctx: PreTradeContext
    ) -> PolicyVerdict | None:
        """Delegate to the existing :class:`RiskManager.check_pretrade_v2`."""
        if ctx.equity_usd is None or ctx.equity_usd <= 0:
            return None
        try:
            from aqp.risk.manager import PreTradeContext as LegacyCtx, RiskManager
        except Exception:  # noqa: BLE001
            return None
        price = order.limit_price or ctx.mark_price
        if price is None:
            return None
        legacy_ctx = LegacyCtx(
            equity=float(ctx.equity_usd),
            cash=float(ctx.cash_usd or 0),
            margin_used=0.0,
            intraday_pnl=0.0,
            session_peak_equity=float(ctx.equity_usd),
            positions={},
            order_notional=float(price * order.quantity),
            order_symbol=order.symbol,
            is_paper=True,
        )
        breaches = RiskManager().check_pretrade_v2(legacy_ctx)
        if not breaches:
            return None
        worst = max(
            (b for b in breaches),
            key=lambda b: 2 if b.severity == "critical" else (1 if b.severity == "block" else 0),
        )
        severity = "block" if worst.severity in ("block", "critical") else "warn"
        return PolicyVerdict(
            policy=f"legacy:{worst.kind}",
            severity=severity,
            reason=worst.message,
            citation="aqp.risk.manager.RiskManager.check_pretrade_v2",
        )


def _worst_severity(verdicts: Iterable[PolicyVerdict]) -> str:
    rank = {"allow": 0, "warn": 1, "block": 2}
    worst = "allow"
    for v in verdicts:
        if rank[v.severity] > rank[worst]:
            worst = v.severity
    return worst


__all__ = ["PreTradeRiskEngine", "PreTradeVerdict"]
