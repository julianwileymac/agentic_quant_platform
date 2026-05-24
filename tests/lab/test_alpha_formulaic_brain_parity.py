"""WorldQuant BRAIN operator parity tests for the symbolic alpha DSL.

The Phase 2 blueprint requires the formulaic-alpha DSL to ship the
BRAIN operator vocabulary verbatim so a formula written against
BRAIN's documentation compiles + runs without translation. We
cross-check NaN handling, group-membership resolution, and lookback
inclusion against deterministic small fixtures so silent divergence
becomes a test failure rather than a runtime surprise.

Operator parity covered here:

- ``ts_zscore(x, n)``
- ``ts_regression(y, x, n)``
- ``trade_when(entry, alpha, exit)``
- ``if_else(condition, then, else)``
- ``decay_linear(x, n)``

Per the plan §16 "BRAIN parity test divergence" trigger, any failure
here means stop shipping new formulaic alphas until parity is green.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from aqp.data.expressions_dsl import (
    SYMBOLIC_OPERATORS,
    SymbolicAlphaError,
    compile_to_factor_node,
)


# ---------------------------------------------------------------------------
# Registry sanity
# ---------------------------------------------------------------------------


def test_brain_operators_registered() -> None:
    for name in ("ts_zscore", "ts_regression", "trade_when", "if_else", "decay_linear"):
        assert name in SYMBOLIC_OPERATORS, f"missing BRAIN alias {name!r}"


def test_brain_aliases_are_callable() -> None:
    for name in ("ts_zscore", "ts_regression", "trade_when", "if_else", "decay_linear"):
        assert callable(SYMBOLIC_OPERATORS[name])


# ---------------------------------------------------------------------------
# ts_zscore semantics
# ---------------------------------------------------------------------------


def test_ts_zscore_known_window() -> None:
    """3-bar z-score of [1,2,3,4,5] at index 4 == (5 - mean[3,4,5]) / std[3,4,5]."""
    series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    result = SYMBOLIC_OPERATORS["ts_zscore"](series, 3)
    assert pd.isna(result.iloc[0])
    assert pd.isna(result.iloc[1])
    last = result.iloc[-1]
    window = series.iloc[-3:]
    expected = (window.iloc[-1] - window.mean()) / window.std(ddof=1)
    assert abs(last - expected) < 1e-9


def test_ts_zscore_zero_std_returns_nan() -> None:
    """Flat series returns NaN — never inf."""
    series = pd.Series([3.0, 3.0, 3.0, 3.0])
    result = SYMBOLIC_OPERATORS["ts_zscore"](series, 2)
    assert pd.isna(result.iloc[-1])
    assert not np.isinf(result.iloc[-1])


def test_ts_zscore_window_under_2_raises() -> None:
    series = pd.Series([1.0, 2.0, 3.0])
    with pytest.raises(SymbolicAlphaError):
        SYMBOLIC_OPERATORS["ts_zscore"](series, 1)


def test_ts_zscore_rejects_scalar() -> None:
    with pytest.raises(SymbolicAlphaError):
        SYMBOLIC_OPERATORS["ts_zscore"](42.0, 3)


# ---------------------------------------------------------------------------
# ts_regression semantics
# ---------------------------------------------------------------------------


def test_ts_regression_unit_slope() -> None:
    """y == 2 * x ⇒ slope ≈ 2."""
    x = pd.Series(np.arange(10, dtype=float))
    y = 2.0 * x
    result = SYMBOLIC_OPERATORS["ts_regression"](y, x, 5)
    assert abs(result.iloc[-1] - 2.0) < 1e-9


def test_ts_regression_zero_variance_returns_nan() -> None:
    """x is constant ⇒ slope is undefined ⇒ NaN."""
    x = pd.Series([4.0, 4.0, 4.0, 4.0, 4.0])
    y = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    result = SYMBOLIC_OPERATORS["ts_regression"](y, x, 3)
    assert pd.isna(result.iloc[-1])


def test_ts_regression_window_under_2_raises() -> None:
    series = pd.Series([1.0, 2.0, 3.0])
    with pytest.raises(SymbolicAlphaError):
        SYMBOLIC_OPERATORS["ts_regression"](series, series, 1)


# ---------------------------------------------------------------------------
# trade_when semantics
# ---------------------------------------------------------------------------


def test_trade_when_holds_alpha_until_exit() -> None:
    """Enter on bar 1, exit on bar 4."""
    alpha = pd.Series([0.1, 0.2, 0.3, 0.4, 0.5])
    entry = pd.Series([False, True, False, False, False])
    exit_ = pd.Series([False, False, False, True, False])
    result = SYMBOLIC_OPERATORS["trade_when"](entry, alpha, exit_)
    assert pd.isna(result.iloc[0])
    assert result.iloc[1] == 0.2
    assert result.iloc[2] == 0.2  # held
    assert pd.isna(result.iloc[3])  # exited
    assert pd.isna(result.iloc[4])


def test_trade_when_exit_takes_precedence_over_entry() -> None:
    """Same-bar exit + entry ⇒ NaN (BRAIN parity: exit wins)."""
    alpha = pd.Series([0.5, 0.5, 0.5])
    entry = pd.Series([False, True, False])
    exit_ = pd.Series([False, True, False])
    result = SYMBOLIC_OPERATORS["trade_when"](entry, alpha, exit_)
    assert pd.isna(result.iloc[1])


def test_trade_when_scalar_conditions_broadcast() -> None:
    alpha = pd.Series([1.0, 2.0, 3.0])
    result = SYMBOLIC_OPERATORS["trade_when"](True, alpha, False)
    # Every entry is True so the alpha passes through unchanged.
    assert list(result.values) == [1.0, 2.0, 3.0]


# ---------------------------------------------------------------------------
# if_else semantics
# ---------------------------------------------------------------------------


def test_if_else_series_condition() -> None:
    condition = pd.Series([True, False, True, False])
    then = pd.Series([10.0, 11.0, 12.0, 13.0])
    other = pd.Series([-1.0, -2.0, -3.0, -4.0])
    result = SYMBOLIC_OPERATORS["if_else"](condition, then, other)
    assert list(result.values) == [10.0, -2.0, 12.0, -4.0]


def test_if_else_scalar_condition() -> None:
    assert SYMBOLIC_OPERATORS["if_else"](True, 1.0, -1.0) == 1.0
    assert SYMBOLIC_OPERATORS["if_else"](False, 1.0, -1.0) == -1.0


def test_if_else_broadcasts_scalar_branches() -> None:
    condition = pd.Series([True, False, True])
    result = SYMBOLIC_OPERATORS["if_else"](condition, 1.0, 0.0)
    assert list(result.values) == [1.0, 0.0, 1.0]


# ---------------------------------------------------------------------------
# decay_linear semantics
# ---------------------------------------------------------------------------


def test_decay_linear_weights_sum_to_one() -> None:
    """Weights for window=n are 1..n normalised — sum to one."""
    series = pd.Series([1.0, 1.0, 1.0, 1.0, 1.0])
    result = SYMBOLIC_OPERATORS["decay_linear"](series, 3)
    # All inputs == 1, weights sum to 1 ⇒ output == 1.
    assert abs(result.iloc[-1] - 1.0) < 1e-9


def test_decay_linear_newer_bars_weighted_more() -> None:
    """Weighted average of [1, 2, 3] with linear-weight = 1·1+2·2+3·3 / 6 = 14/6."""
    series = pd.Series([1.0, 2.0, 3.0])
    result = SYMBOLIC_OPERATORS["decay_linear"](series, 3)
    expected = (1.0 * 1 + 2.0 * 2 + 3.0 * 3) / 6.0
    assert abs(result.iloc[-1] - expected) < 1e-9


def test_decay_linear_window_too_small_raises() -> None:
    series = pd.Series([1.0, 2.0, 3.0])
    with pytest.raises(SymbolicAlphaError):
        SYMBOLIC_OPERATORS["decay_linear"](series, 0)


# ---------------------------------------------------------------------------
# End-to-end DSL compilation
# ---------------------------------------------------------------------------


def _bars(n: int = 30, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    high = close + 0.5
    low = close - 0.5
    open_ = np.concatenate(([close[0]], close[:-1]))
    volume = np.full(n, 100.0)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})


def test_compile_ts_zscore_formula_runs() -> None:
    """End-to-end: parse + compile + compute a BRAIN-style formula."""
    node = compile_to_factor_node("ts_zscore($close, 5)")
    bars = _bars()
    out = node.compute(bars)
    assert isinstance(out, pd.Series)
    # First (window-1) entries are NaN under min_periods=window.
    assert pd.isna(out.iloc[3])
    assert not pd.isna(out.iloc[-1])
    assert "ts_zscore" in node.used_operators


def test_compile_trade_when_with_if_else_runs() -> None:
    """Wrap trade_when around an if_else gate so both operators are exercised.

    Uses the function-form comparison operators (``Gt`` / ``Lt``) the
    AST sandbox allows; the raw ``>`` / ``<`` Compare nodes are
    intentionally rejected by the validator so the DSL stays narrow.
    """
    formula = (
        "trade_when("
        "if_else(Gt($close, 100), 1, 0),"
        " Sign($close - 100),"
        " if_else(Lt($close, 95), 1, 0)"
        ")"
    )
    node = compile_to_factor_node(formula)
    bars = _bars(n=40)
    out = node.compute(bars)
    assert isinstance(out, pd.Series)
    # trade_when never returns a value the underlying alpha cannot
    # produce — Sign() ∈ {-1, 0, 1}, NaN.
    nan_mask = out.isna()
    non_nan = out[~nan_mask].unique()
    assert set(non_nan).issubset({-1.0, 0.0, 1.0})


def test_compile_decay_linear_formula_runs() -> None:
    node = compile_to_factor_node("decay_linear($close - $open, 3)")
    bars = _bars(n=20)
    out = node.compute(bars)
    assert isinstance(out, pd.Series)
    assert pd.isna(out.iloc[1])
    assert not pd.isna(out.iloc[-1])
    assert "decay_linear" in node.used_operators


def test_compile_rejects_unknown_brain_alias() -> None:
    """Operator names not on the whitelist still raise — typo prevention."""
    with pytest.raises(SymbolicAlphaError):
        compile_to_factor_node("ts_winsorize($close, 5)")


def test_compile_rejects_keyword_arguments() -> None:
    """Existing whitelist still rejects keyword args even on new aliases."""
    with pytest.raises(SymbolicAlphaError):
        compile_to_factor_node("ts_zscore(x=$close, n=5)")
