"""Obizhaeva-Wang dynamic execution as a :class:`LobStrategy`.

Wraps the closed-form solver in :mod:`aqp.optimal_control.obizhaeva_wang`
to drive a single liquidation campaign through the LOB engine. The
strategy is *stateful by design*: it fires the initial discrete chunk
on the first event, then emits one small market order per tick at the
optimal continuous rate, and finally clears the remainder at horizon.

Designed to be used together with
:func:`aqp.analysis.flows.optimal_control.obizhaeva_wang_solve_flow`
which sizes ``total_shares`` / ``horizon`` / ``resilience`` against a
calibrated book impact model.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging

from aqp.core.registry import register
from aqp.optimal_control.obizhaeva_wang import (
    ObizhaevaWangParams,
    ObizhaevaWangResult,
    solve as solve_ow,
)
from aqp.strategies.lob import LobState, LobStrategy, OrderIntent

logger = logging.getLogger(__name__)


@dataclass
class _OWExecutionState:
    """Mutable state for the OW execution loop."""

    plan: ObizhaevaWangResult | None = None
    start_time: datetime | None = None
    executed: float = 0.0
    fired_initial: bool = False
    fired_terminal: bool = False
    last_emit_time: datetime | None = None


@register(
    "ObizhaevaWangExecution",
    source="research_report_2026",
    category="execution",
    kind="execution",
)
class ObizhaevaWangExecution(LobStrategy):
    """Discrete-continuous-discrete execution per Obizhaeva-Wang (2013).

    Parameters
    ----------
    total_shares
        Signed quantity to execute. Positive = buy, negative = sell.
    horizon_seconds
        Total execution window in seconds.
    resilience
        Book resilience :math:`\\rho`. Set from a calibration of how
        quickly the book replenishes after a market order; higher =
        more patient liquidation pays off.
    impact_coeff
        Linear price-impact coefficient :math:`\\lambda`.
    tick_quantity
        Approximate per-event execution quantity for the continuous
        phase; the strategy will emit one IOC order per event sized so
        the running cumulative trade tracks the planned trajectory.
    """

    strategy_id = "ow_execution"

    def __init__(
        self,
        total_shares: float = 100.0,
        horizon_seconds: float = 3_600.0,
        resilience: float = 1.0,
        impact_coeff: float = 1.0,
        tick_quantity: float = 1.0,
    ) -> None:
        self.total_shares = float(total_shares)
        self.horizon_seconds = float(horizon_seconds)
        self.resilience = float(resilience)
        self.impact_coeff = float(impact_coeff)
        self.tick_quantity = float(tick_quantity)
        self._state = _OWExecutionState()

    def _ensure_plan(self, now: datetime) -> ObizhaevaWangResult:
        if self._state.plan is not None:
            return self._state.plan
        # Use the horizon in seconds for the solver — the model is
        # scale-invariant in horizon so the units only matter for the
        # continuous-rate interpretation.
        plan = solve_ow(
            ObizhaevaWangParams(
                total_shares=abs(self.total_shares),
                horizon=self.horizon_seconds,
                resilience=self.resilience,
                impact_coeff=self.impact_coeff,
            )
        )
        self._state.plan = plan
        self._state.start_time = now
        return plan

    def _direction(self) -> str:
        return "buy" if self.total_shares > 0 else "sell"

    def _ioc(self, state: LobState, qty: float, tag: str) -> OrderIntent:
        side = self._direction()
        return OrderIntent(
            side=side,  # type: ignore[arg-type]
            price=state.best_ask if side == "buy" else state.best_bid,
            quantity=float(qty),
            order_type="market",
            time_in_force="ioc",
            post_only=False,
            tag=tag,
        )

    def on_event(self, state: LobState) -> list[OrderIntent]:
        plan = self._ensure_plan(state.timestamp)
        start = self._state.start_time or state.timestamp
        elapsed = (state.timestamp - start).total_seconds()
        intents: list[OrderIntent] = []

        # 1) Initial discrete chunk at t = 0.
        if not self._state.fired_initial:
            chunk = plan.initial_chunk
            if chunk > 0:
                intents.append(self._ioc(state, chunk, "ow_initial"))
                self._state.executed += chunk
            self._state.fired_initial = True
            self._state.last_emit_time = state.timestamp
            return intents

        # 2) Terminal discrete chunk once we've crossed the horizon.
        if elapsed >= self.horizon_seconds and not self._state.fired_terminal:
            remainder = abs(self.total_shares) - self._state.executed
            if remainder > 1e-9:
                intents.append(self._ioc(state, remainder, "ow_terminal"))
                self._state.executed += remainder
            self._state.fired_terminal = True
            return intents

        # 3) Continuous flow between the two discrete trades.
        if not self._state.fired_terminal and elapsed > 0:
            # Target cumulative quantity by ``elapsed`` per the OW plan.
            target = plan.initial_chunk + plan.continuous_rate * elapsed
            target = min(target, abs(self.total_shares) - plan.terminal_chunk)
            delta = target - self._state.executed
            if delta > self.tick_quantity * 0.5:
                qty = min(delta, self.tick_quantity)
                intents.append(self._ioc(state, qty, "ow_continuous"))
                self._state.executed += qty
                self._state.last_emit_time = state.timestamp

        return intents


# Sentinel imports for compatibility with `__init__` re-exports.
__all__ = ["ObizhaevaWangExecution", "_OWExecutionState"]

# Suppress unused-symbol lint when JAX is missing.
_ = timedelta  # noqa: F841
_ = field  # noqa: F841
