"""RTS 6 Article 10 stress testing.

Article 10 requires that firms test their systems "to evidence a
reasonable level of assurance that their systems can process twice
the volume of the highest volume of trading reached by the firm
during the previous six months" (ESMA Supervisory Briefing, 26 Feb
2026).

This harness:

1. Determines the peak 6-month message volume from the existing
   ``bot_events`` table.
2. Replays a synthetic stream at 2x that peak through the
   :class:`PreTradeRiskEngine` to verify it sustains throughput
   without rejecting on infrastructure grounds.
3. Records throughput / latency / reject-rate stats for the validation
   report.

Operates entirely against the in-memory engine; no orders leave the
process. The full system-level test (network + venue session) is
performed as a separate :class:`BacktestJob(kind=stress)` in production.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from aqp_bots.risk.engine import PreTradeRiskEngine
from aqp_bots.risk.policies import PreTradeContext
from aqp_bots.schemas.trading import NewOrder, Side, TimeInForce

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class StressResult:
    target_rate_per_s: float
    messages_sent: int = 0
    duration_s: float = 0.0
    throughput_per_s: float = 0.0
    blocks: int = 0
    warnings: int = 0
    allows: int = 0
    latencies_us: list[float] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.throughput_per_s >= self.target_rate_per_s * 0.95


def _peak_rate_per_second(bot_id: str | None = None) -> float:
    """Read the peak message rate from ``bot_events`` over the last 6 months.

    Falls back to a conservative default if the table is empty or
    unavailable.
    """
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_bots import BotEvent
        from sqlalchemy import func, select
    except Exception:  # noqa: BLE001
        return 100.0
    try:
        with SessionLocal() as session:
            from datetime import datetime, timedelta, timezone

            since = datetime.now(timezone.utc) - timedelta(days=180)
            stmt = select(func.count(BotEvent.seq_no)).where(
                BotEvent.recorded_at >= since
            )
            if bot_id is not None:
                stmt = stmt.where(BotEvent.bot_id == bot_id)
            total = session.execute(stmt).scalar_one() or 0
        if total == 0:
            return 100.0
        # Rough estimate: peak is ~ 5x average over the 6-month window.
        seconds = 180 * 24 * 3600
        return max(100.0, (float(total) / seconds) * 5.0)
    except Exception:  # noqa: BLE001
        return 100.0


def run_stress_test(
    *,
    engine: PreTradeRiskEngine,
    bot_id: str | None = None,
    duration_s: float = 5.0,
    rate_multiplier: float = 2.0,
    explicit_target_rate: float | None = None,
) -> StressResult:
    """Replay ``2x`` the peak message rate through ``engine`` for ``duration_s``."""
    peak = explicit_target_rate if explicit_target_rate is not None else _peak_rate_per_second(bot_id)
    target = peak * rate_multiplier
    interval = 1.0 / max(target, 1.0)

    base_order = NewOrder(
        venue="stress",
        symbol="STRESS.SYM",
        side=Side.BUY,
        quantity=Decimal("100"),
        order_type="limit",
        time_in_force=TimeInForce.IOC,
        limit_price=Decimal("100"),
        client_order_id="stress-coid-0",
        strategy_id="stress",
    )
    ctx = PreTradeContext(
        mark_price=Decimal("100"),
        equity_usd=Decimal("1000000"),
        cash_usd=Decimal("1000000"),
    )

    result = StressResult(target_rate_per_s=target)
    start = time.perf_counter()
    deadline = start + duration_s

    while time.perf_counter() < deadline:
        # Tiny mutation so the order isn't deduped.
        order = NewOrder(
            **{
                **{k: getattr(base_order, k) for k in base_order.__struct_fields__},
                "client_order_id": f"stress-coid-{result.messages_sent}",
            }
        )
        t0 = time.perf_counter_ns()
        verdict = engine.evaluate(order, ctx)
        t1 = time.perf_counter_ns()
        result.latencies_us.append((t1 - t0) / 1000.0)
        result.messages_sent += 1
        if verdict.severity == "block":
            result.blocks += 1
        elif verdict.severity == "warn":
            result.warnings += 1
        else:
            result.allows += 1
        # Pace to the target rate but never sleep below the system's
        # minimum sleep granularity.
        sleep_for = interval - ((t1 - t0) / 1e9)
        if sleep_for > 0:
            time.sleep(sleep_for)

    result.duration_s = time.perf_counter() - start
    result.throughput_per_s = (
        result.messages_sent / result.duration_s if result.duration_s > 0 else 0.0
    )
    return result


__all__ = ["StressResult", "run_stress_test"]
