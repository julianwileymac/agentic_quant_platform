"""RiskManager — runtime pre-order checks + post-hoc backtest audits."""
from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from sqlalchemy import select

from aqp.persistence.db import get_session
from aqp.persistence.models import BacktestRun, Fill
from aqp.risk.kill_switch import is_engaged
from aqp.risk.limits import LimitBreach, RiskLimits

logger = logging.getLogger(__name__)


class RiskManager:
    """The single source of truth for hard limits."""

    def __init__(self, limits: RiskLimits | None = None) -> None:
        self.limits = limits or RiskLimits()

    def check_pretrade(
        self,
        equity: float,
        positions: dict[str, Any],
        order_notional: float,
        order_symbol: str,
    ) -> list[LimitBreach]:
        breaches: list[LimitBreach] = []
        if equity <= 0:
            return breaches

        if is_engaged():
            breaches.append(
                LimitBreach(
                    kind="kill_switch",
                    message="Kill switch engaged — rejecting order",
                    value=1.0,
                    limit=0.0,
                    severity="critical",
                )
            )
            return breaches

        pos = positions.get(order_symbol)
        current_notional = 0.0
        if pos:
            current_notional = float(pos.quantity) * float(pos.average_price)
        new_pos_pct = (current_notional + order_notional) / equity
        if new_pos_pct > self.limits.max_position_pct:
            breaches.append(
                LimitBreach(
                    kind="position",
                    message=f"Position on {order_symbol} would exceed cap",
                    value=new_pos_pct,
                    limit=self.limits.max_position_pct,
                    severity="block",
                )
            )
        return breaches

    def audit_backtest(self, backtest_id: str) -> dict[str, Any]:
        """Post-hoc audit: check the completed ledger for limit breaches."""
        breaches: list[LimitBreach] = []
        with get_session() as session:
            run = session.execute(
                select(BacktestRun).where(BacktestRun.id == backtest_id)
            ).scalar_one_or_none()
            if run is None:
                return {"error": f"no backtest {backtest_id}"}
            fills = session.execute(
                select(Fill).order_by(Fill.created_at)
            ).scalars().all()

            if run.max_drawdown is not None and abs(run.max_drawdown) > self.limits.max_drawdown_pct:
                breaches.append(
                    LimitBreach(
                        kind="drawdown",
                        message="Max drawdown exceeded limit",
                        value=abs(run.max_drawdown),
                        limit=self.limits.max_drawdown_pct,
                        severity="block",
                    )
                )

            if run.initial_cash and fills:
                notionals: dict[str, float] = {}
                for f in fills:
                    sign = 1.0 if f.side == "buy" else -1.0
                    notionals[f.vt_symbol] = notionals.get(f.vt_symbol, 0.0) + sign * f.quantity * f.price
                total_gross = sum(abs(v) for v in notionals.values())
                if total_gross > 0:
                    max_conc = max(abs(v) for v in notionals.values()) / total_gross
                    if max_conc > self.limits.max_concentration_pct:
                        breaches.append(
                            LimitBreach(
                                kind="concentration",
                                message="Single-name concentration too high",
                                value=max_conc,
                                limit=self.limits.max_concentration_pct,
                                severity="warn",
                            )
                        )

        return {
            "backtest_id": backtest_id,
            "breaches": [asdict(b) for b in breaches],
            "passed": not any(b.severity == "block" for b in breaches),
            "limits": asdict(self.limits),
        }
