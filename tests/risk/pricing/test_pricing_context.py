"""Tests for the Phase 4 PricingContext + polymorphic ``calc`` dispatch."""
from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from aqp.risk.pricing import (
    PricingContext,
    PricingFuture,
    RiskMeasure,
    calc,
    current_context,
    register_measure,
)


# ---------------------------------------------------------------------------
# Test instrument with a couple of handlers registered for the test suite
# ---------------------------------------------------------------------------


class _FakeOption:
    """Minimal stand-in so the dispatcher has something to route."""

    def __init__(self, strike: float, vol: float = 0.2) -> None:
        self.strike = strike
        self.vol = vol


@register_measure("_FakeOption", RiskMeasure.PRICE)
def _fake_option_price(option: _FakeOption, *, context: PricingContext) -> float:
    """Stub price = strike / 10."""
    return option.strike / 10.0


@register_measure("_FakeOption", RiskMeasure.DELTA)
def _fake_option_delta(option: _FakeOption, *, context: PricingContext) -> float:
    """Stub delta = vol * 2.5."""
    return option.vol * 2.5


# ---------------------------------------------------------------------------
# PricingContext lifecycle
# ---------------------------------------------------------------------------


def test_context_is_none_outside_with_block():
    assert current_context() is None


def test_context_is_active_inside_with_block():
    with PricingContext(as_of=datetime(2026, 5, 16)) as ctx:
        active = current_context()
        assert active is ctx
        assert active.as_of == datetime(2026, 5, 16)
    assert current_context() is None


def test_async_context_manager_works():
    async def main():
        async with PricingContext(dispatch="sync") as ctx:
            assert current_context() is ctx
        assert current_context() is None

    asyncio.run(main())


def test_nested_contexts_restore_previous():
    """Inner context wins inside its block; outer is restored on exit."""
    with PricingContext(as_of=datetime(2026, 1, 1)) as outer:
        assert current_context() is outer
        with PricingContext(as_of=datetime(2026, 6, 1)) as inner:
            assert current_context() is inner
        assert current_context() is outer
    assert current_context() is None


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def test_calc_sync_returns_pricing_future_with_value():
    option = _FakeOption(strike=200)
    with PricingContext(dispatch="sync"):
        future = calc(option, RiskMeasure.PRICE)
    assert isinstance(future, PricingFuture)
    assert future.mode == "sync"
    assert future.value == 20.0
    assert future.done() is True


def test_calc_returns_error_for_unregistered_measure():
    option = _FakeOption(strike=200)
    with PricingContext(dispatch="sync"):
        future = calc(option, RiskMeasure.VAR_95)
    assert future.error is not None
    assert "no handler" in future.error


def test_calc_without_active_context_falls_back_to_sync():
    """calc() outside a ``with`` block uses default sync dispatch."""
    option = _FakeOption(strike=300)
    future = calc(option, RiskMeasure.PRICE)
    assert future.mode == "sync"
    assert future.value == 30.0


def test_calc_async_returns_future_to_be_awaited():
    """In async dispatch mode, calc() returns a coroutine-wrapping future."""
    option = _FakeOption(strike=400)
    with PricingContext(dispatch="async"):
        future = calc(option, RiskMeasure.PRICE)
    assert future.mode == "async"
    assert future.value is None  # not yet awaited

    async def _drive():
        return await future.aresult()

    value = asyncio.run(_drive())
    assert value == 40.0


def test_calc_handler_resolution_walks_mro():
    """Subclass instruments inherit handlers from the parent class."""

    class _DeepFakeOption(_FakeOption):
        pass

    option = _DeepFakeOption(strike=500)
    with PricingContext(dispatch="sync"):
        future = calc(option, RiskMeasure.PRICE)
    # Handler is registered for "_FakeOption" -- the MRO walk should find it.
    assert future.error is None
    assert future.value == 50.0


# ---------------------------------------------------------------------------
# RiskMeasure enum
# ---------------------------------------------------------------------------


def test_risk_measure_enum_carries_expected_families():
    """Every family the dispatch needs is enumerated."""
    expected = {
        "PRICE",
        "DELTA",
        "GAMMA",
        "THETA",
        "VEGA",
        "RHO",
        "VAR_95",
        "VAR_99",
        "TVAR_95",
        "TVAR_99",
        "IR_DELTA",
        "EQ_DELTA",
        "MARGINAL_VAR",
        "COMPONENT_VAR",
        "STRESS_LOSS",
    }
    actual = {m.name for m in RiskMeasure}
    assert expected.issubset(actual)
