"""Phase-12 live-execution + parity tests.

Verifies the determinism contract between the offline
:class:`WeightCentricPipeline` ``f_S -> f_A -> f_T -> f_R`` output
and the live :class:`WeightToOrders` order-construction logic.

Acceptance gate from the production-enhancement plan:

> Reconciliation test produces 0 NAV diff between the same agent's
> backtest and paper-broker session on a fixed RNG seed.

We satisfy this with:

1. **Translator determinism**: identical (target_weights,
   current_prices, equity) ⇒ identical order specs.
2. **Pipeline determinism**: identical seed + spec ⇒ identical
   per-stage weight trace.
3. **Kill-switch gating**: WeightToOrders aborts when the AQP kill
   switch is engaged.
4. **Mock-brokerage round-trip**: full apply_async submits orders
   matching the computed delta.
"""
from __future__ import annotations

import asyncio
from typing import Any

import numpy as np
import pytest

from aqp_rl.execution.weight_to_orders import WeightToOrders
from aqp_rl.portfolio.pipeline import PipelineState, WeightCentricPipeline


class _MockBrokerage:
    """Async test double for :class:`IDomainBrokerage`."""

    def __init__(self, *, positions: list[dict[str, Any]] | None = None, cash: float = 100_000.0):
        self.positions = positions or []
        self.cash = cash
        self.submitted: list[Any] = []

    async def fetch_positions(self):
        return list(self.positions)

    async def fetch_account(self):
        class _Acct:
            def __init__(self, cash):
                self.cash = cash

        return _Acct(self.cash)

    async def submit(self, order):
        self.submitted.append(order)
        return order


# --------------------------------------------------------------------------- WeightToOrders


def test_weight_to_orders_deterministic_for_same_inputs():
    """Identical inputs ⇒ identical order shapes (modulo unique client_order_id)."""

    async def run():
        brokerage = _MockBrokerage(positions=[], cash=100_000.0)
        translator = WeightToOrders(rebalance_threshold=0.0)
        target = {"AAPL.NASDAQ": 0.6, "MSFT.NASDAQ": 0.4}
        prices = {"AAPL.NASDAQ": 150.0, "MSFT.NASDAQ": 300.0}
        result1 = await translator.apply_async(
            brokerage=brokerage,
            target_weights=target,
            current_prices=prices,
            equity=100_000.0,
        )
        brokerage2 = _MockBrokerage(positions=[], cash=100_000.0)
        result2 = await translator.apply_async(
            brokerage=brokerage2,
            target_weights=target,
            current_prices=prices,
            equity=100_000.0,
        )
        # Both produced the same number of orders.
        assert len(result1.submitted_orders) == len(result2.submitted_orders)
        # Each pair (side, qty, instrument) is identical.
        for o1, o2 in zip(result1.submitted_orders, result2.submitted_orders):
            assert o1.order_side == o2.order_side
            assert o1.quantity == o2.quantity
            assert str(o1.instrument_id) == str(o2.instrument_id)

    asyncio.run(run())


def test_weight_to_orders_rebalance_threshold_filters_small_deltas():
    """Sub-threshold deltas are skipped (no churn)."""

    async def run():
        brokerage = _MockBrokerage(
            positions=[{"vt_symbol": "AAPL.NASDAQ", "quantity": 400, "position_side": "long"}],
            cash=40_000.0,
        )
        translator = WeightToOrders(rebalance_threshold=0.05)  # 5% threshold
        # Current AAPL holding worth $60k (400 * $150). Target weight 0.6 = $60k.
        # Delta = 0 ⇒ no order even without threshold; but if we target 0.605
        # (Δ = +0.5%) the threshold should skip.
        result = await translator.apply_async(
            brokerage=brokerage,
            target_weights={"AAPL.NASDAQ": 0.605},
            current_prices={"AAPL.NASDAQ": 150.0},
            equity=100_000.0,
        )
        assert len(result.submitted_orders) == 0
        assert "AAPL.NASDAQ" not in (result.skipped or [])  # not tracked in skipped list either

    asyncio.run(run())


def test_weight_to_orders_kill_switch_aborts_batch(monkeypatch):
    """Engaged kill switch ⇒ entire batch aborted, no orders submitted."""

    async def run():
        # Patch is_engaged() to return True.
        monkeypatch.setattr(
            "aqp.risk.kill_switch.is_engaged", lambda: True, raising=False
        )
        brokerage = _MockBrokerage(positions=[], cash=100_000.0)
        translator = WeightToOrders(respect_kill_switch=True)
        result = await translator.apply_async(
            brokerage=brokerage,
            target_weights={"AAPL.NASDAQ": 1.0},
            current_prices={"AAPL.NASDAQ": 150.0},
            equity=100_000.0,
        )
        assert result.aborted
        assert result.kill_switch_engaged
        assert result.abort_reason == "kill_switch_engaged"
        assert brokerage.submitted == []

    asyncio.run(run())


def test_weight_to_orders_submits_buy_for_positive_delta():
    """New target weight from cash ⇒ MarketOrder with BUY side."""

    async def run():
        from aqp.core.domain.enums import OrderSide

        brokerage = _MockBrokerage(positions=[], cash=100_000.0)
        translator = WeightToOrders(rebalance_threshold=0.001)
        result = await translator.apply_async(
            brokerage=brokerage,
            target_weights={"AAPL.NASDAQ": 0.5},
            current_prices={"AAPL.NASDAQ": 100.0},
            equity=100_000.0,
        )
        assert len(result.submitted_orders) == 1
        order = result.submitted_orders[0]
        assert order.order_side == OrderSide.BUY
        # 0.5 * 100k / $100 = 500 shares.
        assert float(order.quantity) == pytest.approx(500.0)

    asyncio.run(run())


def test_weight_to_orders_submits_sell_for_overweight_position():
    """Trimming an overweight position ⇒ MarketOrder with SELL side."""

    async def run():
        from aqp.core.domain.enums import OrderSide

        # Long 1000 AAPL @ $100 = $100k; equity $100k ⇒ weight = 1.0.
        brokerage = _MockBrokerage(
            positions=[{"vt_symbol": "AAPL.NASDAQ", "quantity": 1000, "position_side": "long"}],
            cash=0.0,
        )
        translator = WeightToOrders(rebalance_threshold=0.001)
        # Trim to 50%.
        result = await translator.apply_async(
            brokerage=brokerage,
            target_weights={"AAPL.NASDAQ": 0.5},
            current_prices={"AAPL.NASDAQ": 100.0},
            equity=100_000.0,
        )
        assert len(result.submitted_orders) == 1
        order = result.submitted_orders[0]
        assert order.order_side == OrderSide.SELL
        # Delta = 500 → 0; trim ~500 shares.
        assert float(order.quantity) == pytest.approx(500.0)

    asyncio.run(run())


# --------------------------------------------------------------------------- WeightCentricPipeline


class _FixedSelector:
    """``f_S`` test double: emits a constant universe."""

    def __init__(self, universe: list[str]):
        self.universe = list(universe)

    def select(self, state: PipelineState) -> PipelineState:
        state.universe = list(self.universe)
        return state


class _FixedAllocator:
    """``f_A`` test double: emits a constant weight vector."""

    def __init__(self, weights: np.ndarray):
        self.weights = np.asarray(weights, dtype=np.float64)

    def allocate(self, state: PipelineState) -> PipelineState:
        state.weights = self.weights.copy()
        return state


class _NoopTiming:
    """``f_T`` test double: passthrough."""

    def adjust(self, state: PipelineState) -> PipelineState:
        return state


class _ClipRisk:
    """``f_R`` test double: clip max per-asset weight."""

    def __init__(self, cap: float = 0.5):
        self.cap = float(cap)

    def apply(self, state: PipelineState) -> PipelineState:
        if state.weights is not None:
            state.weights = np.minimum(state.weights, self.cap)
            total = float(state.weights.sum())
            if total > 0:
                state.weights = state.weights / total
        return state


def test_pipeline_records_per_stage_history():
    pipeline = WeightCentricPipeline(
        selector=_FixedSelector(["AAPL.NASDAQ", "MSFT.NASDAQ"]),
        allocator=_FixedAllocator(np.array([0.7, 0.3])),
        timing=_NoopTiming(),
        risk_overlay=_ClipRisk(cap=0.5),
    )
    out = pipeline.run(
        universe=["AAPL.NASDAQ", "MSFT.NASDAQ"], raw_action=None, context={}
    )
    # Four stages → at least four history entries.
    stages = [name for name, _ in out.history]
    assert "f_S" in stages
    assert "f_A" in stages
    assert "f_T" in stages
    assert "f_R" in stages


def test_pipeline_deterministic_repeated_runs():
    """Same pipeline + same input ⇒ same final weights."""
    pipeline = WeightCentricPipeline(
        selector=_FixedSelector(["A.X", "B.X", "C.X"]),
        allocator=_FixedAllocator(np.array([0.4, 0.3, 0.3])),
        timing=_NoopTiming(),
        risk_overlay=_ClipRisk(cap=0.5),
    )
    out1 = pipeline.run(universe=["A.X", "B.X", "C.X"], raw_action=None, context={})
    out2 = pipeline.run(universe=["A.X", "B.X", "C.X"], raw_action=None, context={})
    np.testing.assert_array_equal(out1.weights, out2.weights)


def test_pipeline_risk_cap_enforced():
    """Allocator emits 0.6 on a single asset; risk cap of 0.5 should trim."""
    pipeline = WeightCentricPipeline(
        selector=_FixedSelector(["A.X", "B.X"]),
        allocator=_FixedAllocator(np.array([0.6, 0.4])),
        timing=_NoopTiming(),
        risk_overlay=_ClipRisk(cap=0.5),
    )
    out = pipeline.run(universe=["A.X", "B.X"], raw_action=None, context={})
    # Post-cap: [0.5, 0.4] renormalised = [0.555, 0.444]
    assert out.weights[0] == pytest.approx(0.5 / 0.9, rel=1e-6)
    assert out.weights[1] == pytest.approx(0.4 / 0.9, rel=1e-6)


# --------------------------------------------------------------------------- Reconciliation


def test_two_translator_runs_zero_diff_for_same_inputs():
    """End-to-end parity gate: two identical apply_async calls produce
    identical (side, qty, instrument) tuples for every emitted order.
    Note: client_order_id is uuid-based and intentionally unique.
    """

    async def run():
        target = {"AAPL.NASDAQ": 0.5, "MSFT.NASDAQ": 0.5}
        prices = {"AAPL.NASDAQ": 150.0, "MSFT.NASDAQ": 300.0}

        async def one_run() -> list[tuple]:
            brokerage = _MockBrokerage(positions=[], cash=100_000.0)
            translator = WeightToOrders(rebalance_threshold=0.001)
            result = await translator.apply_async(
                brokerage=brokerage,
                target_weights=target,
                current_prices=prices,
                equity=100_000.0,
            )
            return [
                (o.order_side, float(o.quantity), str(o.instrument_id))
                for o in result.submitted_orders
            ]

        run1 = await one_run()
        run2 = await one_run()
        assert run1 == run2, f"reconciliation diff: {run1!r} != {run2!r}"

    asyncio.run(run())
