"""Tests for the Phase 3 RiskManager.check_pretrade_v2.

Validates that every limit declared in :class:`RiskLimits` is actually
enforced at submit time -- not just at backtest audit time, which was
the pre-Phase-3 gap.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from aqp.risk.limits import LimitBreach, RiskLimits
from aqp.risk.manager import PreTradeContext, RiskManager


@pytest.fixture
def lim() -> RiskLimits:
    """Tight limits so the tests don't need huge fake positions."""
    return RiskLimits(
        max_position_pct=0.10,
        max_daily_loss_pct=0.05,
        max_drawdown_pct=0.10,
        max_concentration_pct=0.50,
        max_gross_exposure=1.0,
    )


@pytest.fixture
def manager(lim: RiskLimits) -> RiskManager:
    return RiskManager(limits=lim)


def _ctx(
    *,
    equity: float = 100_000.0,
    cash: float | None = None,
    margin_used: float = 0.0,
    intraday_pnl: float = 0.0,
    session_peak_equity: float | None = None,
    positions: dict | None = None,
    order_notional: float = 5_000.0,
    order_symbol: str = "AAPL.NASDAQ",
    is_paper: bool = True,
) -> PreTradeContext:
    return PreTradeContext(
        equity=equity,
        cash=cash if cash is not None else equity,
        margin_used=margin_used,
        intraday_pnl=intraday_pnl,
        session_peak_equity=session_peak_equity or equity,
        positions=positions or {},
        order_notional=order_notional,
        order_symbol=order_symbol,
        is_paper=is_paper,
    )


def test_kill_switch_blocks_all_other_checks(manager: RiskManager):
    """When the kill switch is engaged, the manager rejects immediately."""
    with patch("aqp.risk.manager.is_engaged", return_value=True):
        breaches = manager.check_pretrade_v2(_ctx())
    assert any(b.kind == "kill_switch" for b in breaches)
    assert breaches[0].severity == "critical"


def test_daily_loss_blocks_when_intraday_exceeds_cap(manager: RiskManager):
    """Intraday loss > daily cap blocks new orders."""
    # 6% intraday loss vs 5% cap
    ctx = _ctx(intraday_pnl=-6_000.0)
    with patch("aqp.risk.manager.is_engaged", return_value=False):
        breaches = manager.check_pretrade_v2(ctx)
    daily_loss_breach = [b for b in breaches if b.kind == "daily_loss"]
    assert daily_loss_breach
    assert daily_loss_breach[0].severity == "block"


def test_drawdown_blocks_when_session_dd_exceeds_cap(manager: RiskManager):
    """Session drawdown > cap blocks."""
    ctx = _ctx(
        equity=90_000.0,
        session_peak_equity=100_000.0,  # 10% drawdown == cap; bump above
    )
    ctx.session_peak_equity = 101_000.0  # 10.89% drawdown
    with patch("aqp.risk.manager.is_engaged", return_value=False):
        breaches = manager.check_pretrade_v2(ctx)
    assert any(b.kind == "drawdown" and b.severity == "block" for b in breaches)


def test_position_pct_blocks_oversize_single_symbol(manager: RiskManager):
    """Order that would push single-symbol pct above cap is blocked."""
    # Existing position of $8k + new $5k = $13k vs $100k equity = 13%
    ctx = _ctx(
        positions={"AAPL.NASDAQ": {"quantity": 80.0, "average_price": 100.0}},
        order_notional=5_000.0,
    )
    with patch("aqp.risk.manager.is_engaged", return_value=False):
        breaches = manager.check_pretrade_v2(ctx)
    assert any(b.kind == "position" and b.severity == "block" for b in breaches)


def test_gross_exposure_blocks_oversize_book(manager: RiskManager):
    """Total gross book > 100% of equity is blocked."""
    # Existing positions worth 95k in total, order adds 10k more
    ctx = _ctx(
        positions={
            "MSFT.NASDAQ": {"quantity": 200.0, "average_price": 400.0},  # 80k
            "GOOG.NASDAQ": {"quantity": 100.0, "average_price": 150.0},  # 15k
        },
        order_notional=10_000.0,
    )
    with patch("aqp.risk.manager.is_engaged", return_value=False):
        breaches = manager.check_pretrade_v2(ctx)
    assert any(b.kind == "gross_exposure" and b.severity == "block" for b in breaches)


def test_concentration_warns_when_single_name_exceeds_cap(manager: RiskManager):
    """Single-name concentration above cap is WARN, not BLOCK."""
    ctx = _ctx(
        positions={
            "AAPL.NASDAQ": {"quantity": 100.0, "average_price": 60.0},  # 6k
        },
        order_notional=3_000.0,  # AAPL grows to 9k of 9k book = 100%
        order_symbol="AAPL.NASDAQ",
    )
    with patch("aqp.risk.manager.is_engaged", return_value=False):
        breaches = manager.check_pretrade_v2(ctx)
    conc_breaches = [b for b in breaches if b.kind == "concentration"]
    assert conc_breaches
    assert conc_breaches[0].severity == "warn"  # not block


def test_buying_power_blocks_when_insufficient(manager: RiskManager):
    """Live (non-paper) order that exceeds buying power is blocked."""
    ctx = _ctx(
        is_paper=False,
        cash=1_000.0,
        margin_used=100_000.0,
        order_notional=50_000.0,
    )
    with patch("aqp.risk.manager.is_engaged", return_value=False):
        breaches = manager.check_pretrade_v2(ctx)
    assert any(b.kind == "buying_power" and b.severity == "block" for b in breaches)


def test_clean_order_passes_all_checks(manager: RiskManager):
    """Well-behaved order produces zero breaches."""
    ctx = _ctx(order_notional=1_000.0)  # 1% of equity
    with patch("aqp.risk.manager.is_engaged", return_value=False):
        breaches = manager.check_pretrade_v2(ctx)
    assert not breaches


def test_legacy_check_pretrade_still_works(manager: RiskManager):
    """The legacy entry point still respects kill-switch + position cap."""
    with patch("aqp.risk.manager.is_engaged", return_value=False):
        breaches = manager.check_pretrade(
            equity=100_000.0,
            positions={},
            order_notional=1_000.0,
            order_symbol="AAPL.NASDAQ",
        )
    assert not breaches
