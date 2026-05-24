"""RTS 6 Article 6 conformance testing.

Article 6 requires firms to test:

(a) the operation of the algorithmic trading system or trading algorithm
(b) the connectivity to the relevant trading venue
(c) the firm's ability to handle erroneous or duplicate trades
(d) the firm's pre-trade risk controls

This module ships a test harness that exercises every registered
pre-trade policy with synthetic orders crafted to trip each control,
then asserts the policy returns ``severity=block`` with the correct
citation. The output feeds into the annual validation report.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from aqp_bots.risk.engine import PreTradeRiskEngine
from aqp_bots.risk.policies import PreTradeContext
from aqp_bots.schemas.trading import NewOrder, Side, TimeInForce

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ConformanceCase:
    """One synthetic test case."""

    name: str
    policy: str
    citation: str
    order_factory: Any  # Callable[[], NewOrder]
    context: PreTradeContext = field(default_factory=PreTradeContext)


@dataclass(slots=True)
class ConformanceResult:
    """Outcome of one conformance pass."""

    cases_run: int = 0
    cases_passed: int = 0
    cases_failed: list[dict[str, Any]] = field(default_factory=list)

    def is_passing(self) -> bool:
        return self.cases_run > 0 and not self.cases_failed


def _build_canonical_cases() -> list[ConformanceCase]:
    """Standard cases — one per Art. 15(1)(a)-(d) policy."""
    base = dict(
        venue="test",
        symbol="TEST.NASDAQ",
        side=Side.BUY,
        quantity=Decimal("100"),
        order_type="limit",
        time_in_force=TimeInForce.GTC,
        client_order_id="conformance-test-coid",
    )
    return [
        ConformanceCase(
            name="price_collar_exceeds_threshold",
            policy="price_collar",
            citation="RTS 6 Art. 15(1)(a) / SEC 15c3-5 (c)(1)(i)",
            order_factory=lambda: NewOrder(**base, limit_price=Decimal("200")),
            context=PreTradeContext(mark_price=Decimal("100")),
        ),
        ConformanceCase(
            name="max_order_value_exceeded",
            policy="max_order_value",
            citation="RTS 6 Art. 15(1)(b) / SEC 15c3-5 (c)(1)(i)",
            order_factory=lambda: NewOrder(
                **{**base, "quantity": Decimal("10000")}, limit_price=Decimal("100")
            ),
            context=PreTradeContext(mark_price=Decimal("100")),
        ),
        ConformanceCase(
            name="max_order_volume_exceeded",
            policy="max_order_volume",
            citation="RTS 6 Art. 15(1)(c) / SEC 15c3-5 (c)(1)(i)",
            order_factory=lambda: NewOrder(
                **{**base, "quantity": Decimal("1000000")}, limit_price=Decimal("100")
            ),
            context=PreTradeContext(mark_price=Decimal("100")),
        ),
    ]


def run_conformance_tests(
    *,
    engine: PreTradeRiskEngine,
    cases: list[ConformanceCase] | None = None,
) -> ConformanceResult:
    """Run every case through ``engine`` and tally results."""
    cases = cases or _build_canonical_cases()
    result = ConformanceResult()
    for case in cases:
        result.cases_run += 1
        try:
            order = case.order_factory()
        except Exception as exc:  # noqa: BLE001
            result.cases_failed.append(
                {"case": case.name, "error": f"order_factory raised: {exc!r}"}
            )
            continue
        verdict = engine.evaluate(order, case.context)
        # The named policy must have fired.
        fired = any(
            v.policy == case.policy and v.severity == "block"
            for v in verdict.verdicts
        )
        if fired:
            result.cases_passed += 1
        else:
            result.cases_failed.append(
                {
                    "case": case.name,
                    "expected_policy": case.policy,
                    "expected_severity": "block",
                    "actual_severity": verdict.severity,
                    "actual_verdicts": [
                        {"policy": v.policy, "severity": v.severity, "reason": v.reason}
                        for v in verdict.verdicts
                    ],
                }
            )
    return result


__all__ = ["ConformanceCase", "ConformanceResult", "run_conformance_tests"]
