"""Tests for the Phase 5 pricing / arbitrage MCP tools.

The tools' run methods are exercised against fake input data so the
test suite stays hermetic (no DB / no scipy if it isn't installed).
"""
from __future__ import annotations

import pytest

from aqp.data.mcp.base import MCPToolContext


def _ctx() -> MCPToolContext:
    return MCPToolContext(
        actor="test",
        actor_kind="user",
        workspace_id="ws-1",
        project_id="prj-1",
        granted_scopes=("data:read",),
    )


# ---------------------------------------------------------------------------
# data.risk.var.compute
# ---------------------------------------------------------------------------


def test_var_compute_historical_returns_positive_var():
    """Historical VaR is positive for a return series with mass below 0."""
    pytest.importorskip("numpy")
    from aqp.data.mcp.tools.pricing import ComputeVarTool

    # 100 returns, 5% in the left tail at -2%
    returns = [-0.02] * 5 + [0.001] * 95
    tool = ComputeVarTool()
    result = tool.invoke(
        ctx=_ctx(),
        returns=returns,
        confidence=0.95,
        method="historical",
        horizon_days=1,
        notional=1_000_000.0,
    )
    assert result.ok
    assert result.data["var_pct"] > 0
    # TVaR >= VaR (tail mean is more negative)
    assert result.data["tvar_pct"] >= result.data["var_pct"]
    assert result.data["var_dollar"] == pytest.approx(result.data["var_pct"] * 1_000_000.0)


def test_var_compute_horizon_scaling_uses_sqrt_t():
    """20-day VaR is sqrt(20) times 1-day VaR for sqrt-T scaling."""
    pytest.importorskip("numpy")
    from aqp.data.mcp.tools.pricing import ComputeVarTool

    returns = [-0.02] * 5 + [0.001] * 95
    tool = ComputeVarTool()
    var_1d = tool.invoke(
        ctx=_ctx(), returns=returns, confidence=0.95, horizon_days=1,
    ).data["var_pct"]
    var_20d = tool.invoke(
        ctx=_ctx(), returns=returns, confidence=0.95, horizon_days=20,
    ).data["var_pct"]
    assert var_20d == pytest.approx(var_1d * (20 ** 0.5), rel=1e-6)


def test_var_compute_rejects_too_few_observations():
    pytest.importorskip("numpy")
    from aqp.data.mcp.tools.pricing import ComputeVarTool

    tool = ComputeVarTool()
    result = tool.invoke(ctx=_ctx(), returns=[0.0] * 10, confidence=0.95)
    assert result.ok is False


# ---------------------------------------------------------------------------
# data.arbitrage.ah_share_basis
# ---------------------------------------------------------------------------


def test_ah_share_basis_flags_arbitrage():
    from aqp.data.mcp.tools.arbitrage import AHShareBasisTool

    # ICBC: A at 5.00 CNY, H at 6.00 HKD, FX 0.93 CNY/HKD
    # Implied H = 5.00/0.93 = 5.376 HKD -- H is rich vs implied
    tool = AHShareBasisTool()
    result = tool.invoke(
        ctx=_ctx(),
        a_price=5.00,
        h_price=6.00,
        fx_rate=0.93,
        conversion_ratio=1.0,
        threshold_bps=100.0,
    )
    assert result.ok
    assert result.data["is_arbitrage"] is True
    # basis is positive -> buy_a_sell_b
    assert result.data["arbitrage_direction"] == "buy_a_sell_b"


def test_ah_share_basis_no_signal_at_fair_value():
    from aqp.data.mcp.tools.arbitrage import AHShareBasisTool

    tool = AHShareBasisTool()
    result = tool.invoke(
        ctx=_ctx(),
        a_price=5.00,
        h_price=5.376,  # exactly the implied value
        fx_rate=0.93,
    )
    assert result.ok
    assert result.data["is_arbitrage"] is False


# ---------------------------------------------------------------------------
# data.pricing.greeks.option_chain
# ---------------------------------------------------------------------------


def test_option_chain_greeks_returns_per_strike_breakdown():
    pytest.importorskip("scipy")
    from aqp.data.mcp.tools.pricing import OptionChainGreeksTool

    tool = OptionChainGreeksTool()
    result = tool.invoke(
        ctx=_ctx(),
        underlying="AAPL",
        expiry="2026-12-19",
        underlying_price=200.0,
        risk_free_rate=0.045,
        implied_vol_default=0.25,
        strikes=[180.0, 200.0, 220.0],
    )
    assert result.ok
    assert "per_strike" in result.data
    assert len(result.data["per_strike"]) == 3
    # ATM call delta should be ~0.5
    atm = next(r for r in result.data["per_strike"] if r["strike"] == 200.0)
    assert 0.4 < atm["delta_call"] < 0.7


# ---------------------------------------------------------------------------
# data.arbitrage.cointegration_pair
# ---------------------------------------------------------------------------


def test_cointegration_pair_smoke():
    pytest.importorskip("numpy")
    pytest.importorskip("pandas")
    # The engle_granger primitive may not be available in test env;
    # skip if so.
    try:
        from aqp.data.cointegration import engle_granger  # noqa: F401
    except Exception:
        pytest.skip("engle_granger primitive unavailable")

    from aqp.data.mcp.tools.arbitrage import CointegrationPairTool

    import numpy as np
    rng = np.random.default_rng(seed=42)
    n = 200
    common = np.cumsum(rng.normal(0, 1, n))
    a = common + rng.normal(0, 0.5, n)  # cointegrated with common
    b = common + rng.normal(0, 0.5, n)  # cointegrated with common
    tool = CointegrationPairTool()
    result = tool.invoke(
        ctx=_ctx(),
        series_a=list(a),
        series_b=list(b),
        significance_level=0.05,
    )
    assert result.ok
    assert "hedge_ratio" in result.data
    assert "adf_p_value" in result.data
