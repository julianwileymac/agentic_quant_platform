"""RiskManager — runtime pre-order checks + post-hoc backtest audits.

Phase 3 (migration 0042 + 0043) extends pre-trade enforcement beyond
the legacy kill-switch + position-pct pair. Every limit on
:class:`RiskLimits` is now checked at submit time:

* ``max_position_pct`` -- single-symbol notional / equity cap
* ``max_daily_loss_pct`` -- circuit breaker against intraday drawdown
* ``max_drawdown_pct`` -- session-level peak-to-trough cap
* ``max_concentration_pct`` -- single-symbol fraction of gross book
* ``max_gross_exposure`` -- aggregate notional / equity cap

The new method :meth:`RiskManager.check_pretrade_v2` takes a fuller
context (account snapshot, open positions, intraday PnL) so the
checks can be enforced before the order leaves the desk. The legacy
``check_pretrade`` keeps its narrower signature for back-compat with
the existing :class:`PaperTradingSession` consumer.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import select

from aqp.persistence.db import get_session
from aqp.persistence.models import BacktestRun, Fill
from aqp.risk.kill_switch import is_engaged
from aqp.risk.limits import LimitBreach, RiskLimits

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PreTradeContext:
    """Full snapshot needed for Phase 3 pre-trade enforcement.

    The caller (``PaperTradingSession``, REST ``/orders`` route)
    builds this from the current :class:`Account` /
    :class:`AccountBalance` / :class:`AccountPosition` rows. The
    manager treats the context as immutable.
    """

    equity: float
    cash: float
    margin_used: float
    intraday_pnl: float
    session_peak_equity: float
    positions: dict[str, Any] = field(default_factory=dict)
    # vt_symbol -> {"quantity": float, "average_price": float}
    order_notional: float = 0.0
    order_symbol: str = ""
    is_paper: bool = True
    base_currency: str = "USD"


class RiskManager:
    """The single source of truth for hard limits."""

    def __init__(self, limits: RiskLimits | None = None) -> None:
        self.limits = limits or RiskLimits()

    # ------------------------------------------------------------------
    # Legacy surface (kept for the existing PaperTradingSession + tests)
    # ------------------------------------------------------------------

    def check_pretrade(
        self,
        equity: float,
        positions: dict[str, Any],
        order_notional: float,
        order_symbol: str,
    ) -> list[LimitBreach]:
        """Legacy entry point -- kill switch + position-pct only."""
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

    # ------------------------------------------------------------------
    # Phase 3 entry point
    # ------------------------------------------------------------------

    def check_pretrade_v2(self, ctx: PreTradeContext) -> list[LimitBreach]:
        """Full pre-trade enforcement against every limit.

        Returns a list of breaches; the caller MUST reject the order if
        any breach has ``severity == "block"`` or ``"critical"``.
        Warn-severity breaches are returned for logging only.
        """
        breaches: list[LimitBreach] = []
        if ctx.equity <= 0:
            return breaches

        # 1. Kill switch (highest priority)
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

        # 2. Intraday drawdown circuit breaker
        if ctx.intraday_pnl < 0:
            daily_loss_pct = abs(ctx.intraday_pnl) / max(ctx.equity, 1e-9)
            if daily_loss_pct > self.limits.max_daily_loss_pct:
                breaches.append(
                    LimitBreach(
                        kind="daily_loss",
                        message="Intraday loss exceeded daily cap",
                        value=daily_loss_pct,
                        limit=self.limits.max_daily_loss_pct,
                        severity="block",
                    )
                )

        # 3. Session-level drawdown
        if ctx.session_peak_equity > 0:
            drawdown_pct = max(
                0.0,
                (ctx.session_peak_equity - ctx.equity) / ctx.session_peak_equity,
            )
            if drawdown_pct > self.limits.max_drawdown_pct:
                breaches.append(
                    LimitBreach(
                        kind="drawdown",
                        message="Session drawdown exceeded cap",
                        value=drawdown_pct,
                        limit=self.limits.max_drawdown_pct,
                        severity="block",
                    )
                )

        # 4. Single-symbol position-pct cap
        pos = ctx.positions.get(ctx.order_symbol)
        current_notional = 0.0
        if pos:
            current_notional = float(pos.get("quantity", 0.0) or 0.0) * float(
                pos.get("average_price", 0.0) or 0.0
            )
        new_pos_pct = (current_notional + ctx.order_notional) / ctx.equity
        if new_pos_pct > self.limits.max_position_pct:
            breaches.append(
                LimitBreach(
                    kind="position",
                    message=f"Position on {ctx.order_symbol} would exceed cap",
                    value=new_pos_pct,
                    limit=self.limits.max_position_pct,
                    severity="block",
                )
            )

        # 5. Gross exposure cap (book-level)
        total_gross = sum(
            abs(
                float(p.get("quantity", 0.0) or 0.0)
                * float(p.get("average_price", 0.0) or 0.0)
            )
            for sym, p in ctx.positions.items()
            if sym != ctx.order_symbol
        )
        total_gross += abs(current_notional + ctx.order_notional)
        gross_exposure = total_gross / ctx.equity
        if gross_exposure > self.limits.max_gross_exposure:
            breaches.append(
                LimitBreach(
                    kind="gross_exposure",
                    message="Gross exposure would exceed cap",
                    value=gross_exposure,
                    limit=self.limits.max_gross_exposure,
                    severity="block",
                )
            )

        # 6. Single-name concentration (over the new gross book)
        if total_gross > 0:
            target_notional = abs(current_notional + ctx.order_notional)
            concentration = target_notional / total_gross
            if concentration > self.limits.max_concentration_pct:
                breaches.append(
                    LimitBreach(
                        kind="concentration",
                        message=f"{ctx.order_symbol} concentration would exceed cap",
                        value=concentration,
                        limit=self.limits.max_concentration_pct,
                        severity="warn",
                    )
                )

        # 7. Buying-power check (margin accounts) -- when cash < order
        # notional and margin_used is already significant, reject.
        if not ctx.is_paper:
            buying_power = max(0.0, ctx.cash + ctx.equity * 1.0 - ctx.margin_used)
            if ctx.order_notional > buying_power:
                breaches.append(
                    LimitBreach(
                        kind="buying_power",
                        message="Order notional exceeds available buying power",
                        value=ctx.order_notional,
                        limit=buying_power,
                        severity="block",
                    )
                )

        return breaches

    # ------------------------------------------------------------------
    # Post-hoc audit (unchanged)
    # ------------------------------------------------------------------

    def audit_backtest(self, backtest_id: str) -> dict[str, Any]:
        """Post-hoc audit: check the completed ledger for limit breaches."""
        breaches: list[LimitBreach] = []
        with get_session() as session:
            run = session.execute(
                select(BacktestRun).where(BacktestRun.id == backtest_id)
            ).scalar_one_or_none()
            if run is None:
                return {"error": f"no backtest {backtest_id}"}
            fills = (
                session.execute(select(Fill).order_by(Fill.created_at))
                .scalars()
                .all()
            )

            if (
                run.max_drawdown is not None
                and abs(run.max_drawdown) > self.limits.max_drawdown_pct
            ):
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
                    notionals[f.vt_symbol] = (
                        notionals.get(f.vt_symbol, 0.0)
                        + sign * f.quantity * f.price
                    )
                total_gross = sum(abs(v) for v in notionals.values())
                if total_gross > 0:
                    max_conc = (
                        max(abs(v) for v in notionals.values()) / total_gross
                    )
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
