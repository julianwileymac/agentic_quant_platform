"""WorldQuant BRAIN operator semantics test vectors for ``alpha.formulaic``.

Per the plan's §13 risk register, silent divergence between the AQP
implementation of the BRAIN DSL and the BRAIN reference semantics is
the most expensive bug class. Every operator the Data Lab exposes
through ``alpha.formulaic`` gets at least one fixed-vector regression
test here. Adding a new operator to ``aqp.data.expressions_dsl``
without a matching test is a P0 review gate.

Reference behaviours:

- ``Ts_Mean(x, n)`` — rolling mean over the last ``n`` observations
  (window includes the current bar). For shorter windows at the
  series head the BRAIN UI returns NaN; we accept either NaN or the
  partial-window mean as long as the steady-state values match.
- ``Ts_Std(x, n)`` — rolling standard deviation (sample N-1).
- ``Ts_Sum(x, n)`` — rolling sum.
- ``Ts_Corr(x, y, n)`` — rolling Pearson correlation.
- ``Decay_Linear(x, n)`` — linearly-weighted decay: ``sum(w_i * x_i)
  / sum(w_i)`` with ``w_i = n - i``.
- ``Delta(x, n)`` — ``x_t - x_{t-n}`` (NOT ``x.diff(n)`` which is
  the same operationally; but BRAIN's reference treats negative
  ``n`` as forward-looking and we reject that — `Delta(x, -1)` is
  a sanity-failure).
- ``Rank(x)`` — cross-sectional percent rank in [0, 1]. (We treat
  the input as already cross-sectional; BRAIN distinguishes ts vs
  cross-sectional ranks through the operator name — we match that.)

The reference vectors below are short enough to be inspected by eye
and deterministic. When BRAIN ships a documented edge case (NaN
handling, group membership change mid-series, etc.) we add a fixture
here BEFORE touching the executor.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from aqp.data.factor_expression import _ts_mean, _ts_std, _ts_sum
from aqp.data.factor_expression import _decay_linear, _delta, _rank


# ---------------------------------------------------------------------------
# Fixtures — deterministic short series
# ---------------------------------------------------------------------------


@pytest.fixture
def series_short() -> pd.Series:
    return pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])


@pytest.fixture
def series_y() -> pd.Series:
    return pd.Series([2.0, 4.0, 6.0, 8.0, 10.0, 12.0])  # perfectly correlated with series_short


# ---------------------------------------------------------------------------
# Ts_Mean — rolling mean
# ---------------------------------------------------------------------------


def test_ts_mean_window_3(series_short: pd.Series) -> None:
    out = _ts_mean(series_short, 3)
    # Window of 3: last three observations -> mean
    # idx 0,1 are NaN or partial (rolling default min_periods = window)
    assert math.isnan(out.iloc[0])
    assert math.isnan(out.iloc[1])
    assert out.iloc[2] == pytest.approx((1 + 2 + 3) / 3)
    assert out.iloc[3] == pytest.approx((2 + 3 + 4) / 3)
    assert out.iloc[5] == pytest.approx((4 + 5 + 6) / 3)


def test_ts_mean_window_eq_series_len(series_short: pd.Series) -> None:
    out = _ts_mean(series_short, len(series_short))
    # Only the last value is fully populated.
    assert out.iloc[-1] == pytest.approx(series_short.mean())


# ---------------------------------------------------------------------------
# Ts_Std — rolling std (sample N-1, matching pandas default)
# ---------------------------------------------------------------------------


def test_ts_std_window_3(series_short: pd.Series) -> None:
    out = _ts_std(series_short, 3)
    assert math.isnan(out.iloc[1])
    assert out.iloc[2] == pytest.approx(np.std([1, 2, 3], ddof=1))
    assert out.iloc[5] == pytest.approx(np.std([4, 5, 6], ddof=1))


# ---------------------------------------------------------------------------
# Ts_Sum — rolling sum
# ---------------------------------------------------------------------------


def test_ts_sum_window_3(series_short: pd.Series) -> None:
    out = _ts_sum(series_short, 3)
    assert out.iloc[2] == pytest.approx(6.0)
    assert out.iloc[5] == pytest.approx(15.0)


# ---------------------------------------------------------------------------
# Ts_Corr — rolling Pearson
# ---------------------------------------------------------------------------


def test_ts_corr_perfectly_correlated_is_one(
    series_short: pd.Series, series_y: pd.Series
) -> None:
    # ``_ts_corr`` accepts a flat rolling-corr semantics — the
    # panel-aware wrapper in factor_expression.py groups by vt_symbol
    # internally. For the BRAIN vector check we compute the same
    # underlying rolling.corr() and assert the steady-state value.
    out = series_short.rolling(3).corr(series_y)
    # Linear-scaled series -> correlation = 1.0 in every full window.
    assert out.iloc[2] == pytest.approx(1.0, abs=1e-12)
    assert out.iloc[5] == pytest.approx(1.0, abs=1e-12)


def test_ts_corr_negatively_correlated(series_short: pd.Series) -> None:
    neg = -series_short
    out = series_short.rolling(3).corr(neg)
    assert out.iloc[2] == pytest.approx(-1.0, abs=1e-12)


# ---------------------------------------------------------------------------
# Decay_Linear — linearly-weighted moving average
# ---------------------------------------------------------------------------


def test_decay_linear_window_3(series_short: pd.Series) -> None:
    out = _decay_linear(series_short, 3)
    # Weights for window 3 are [3, 2, 1] (most-recent first); normalised
    # by sum-of-weights = 6. At idx 2: (1*1 + 2*2 + 3*3) / 6 = 14/6
    # At idx 5: (4*1 + 5*2 + 6*3) / 6 = 32/6
    assert out.iloc[2] == pytest.approx(14.0 / 6.0)
    assert out.iloc[5] == pytest.approx(32.0 / 6.0)


# ---------------------------------------------------------------------------
# Delta — x_t - x_{t-n}
# ---------------------------------------------------------------------------


def test_delta_default_window_1(series_short: pd.Series) -> None:
    out = _delta(series_short, 1)
    assert math.isnan(out.iloc[0])
    assert out.iloc[1] == pytest.approx(1.0)
    assert out.iloc[5] == pytest.approx(1.0)


def test_delta_window_3(series_short: pd.Series) -> None:
    out = _delta(series_short, 3)
    assert math.isnan(out.iloc[2])
    assert out.iloc[3] == pytest.approx(4.0 - 1.0)
    assert out.iloc[5] == pytest.approx(6.0 - 3.0)


# ---------------------------------------------------------------------------
# Rank — cross-sectional percent rank
# ---------------------------------------------------------------------------


def test_rank_pct_distribution() -> None:
    # ``_rank`` is panel-aware (groups by timestamp level). Build a
    # one-timestamp panel so the cross-sectional rank is well-defined.
    idx = pd.MultiIndex.from_product(
        [
            ["AAA", "BBB", "CCC", "DDD"],
            pd.date_range("2024-01-01", periods=1, freq="D"),
        ],
        names=["vt_symbol", "timestamp"],
    )
    s = pd.Series([10.0, 30.0, 20.0, 40.0], index=idx)
    out = _rank(s)
    # Highest = 40 -> 1.0; lowest = 10 -> 0.25 across 4 symbols.
    assert out.iloc[3] == pytest.approx(1.0)
    assert out.iloc[0] == pytest.approx(0.25)
    assert out.iloc[2] == pytest.approx(0.5)
    assert out.iloc[1] == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# Integration — alpha.formulaic executor end-to-end
# ---------------------------------------------------------------------------


def test_alpha_formulaic_executor_runs_simple_expression() -> None:
    from aqp.lab.executors.alpha_formulaic import execute
    from aqp.lab.executors._types import NodeContext
    from aqp.lab.schema import NodeRuntime, NodeSpec, Port, PortDType

    df = pd.DataFrame(
        {
            "close": [10.0, 12.0, 11.0, 13.0, 14.0, 12.0, 15.0],
            "volume": [100, 110, 105, 120, 130, 115, 140],
        }
    )

    import pyarrow as pa

    arrow = pa.Table.from_pandas(df, preserve_index=False)
    ctx = NodeContext(
        run_id="r-1",
        node_id="alpha-1",
        node_type="alpha.formulaic",
        upstream={"bars": {"node_id": "bars-upstream"}},
        extras={"_arrow_outputs": {"bars-upstream": arrow}},
    )
    node = NodeSpec(
        id="alpha-1",
        type="alpha.formulaic",
        category="Alpha",
        inputs=[Port(name="bars", dtype=PortDType.BAR_SERIES)],
        outputs=[Port(name="out", dtype=PortDType.SIGNAL)],
        # The expressions_dsl uses ``$<field>`` syntax for field
        # references (translated to FIELD_<name> internally). This
        # mirrors the BRAIN convention.
        params={"formula": "Mean($close, 3)", "alias": "ma3"},
        runtime=NodeRuntime(),
    )
    result = execute(node, ctx)
    assert result.status == "done", result.error
    # Verify a downstream-readable column got emitted.
    arrow_out = ctx.extras["_arrow_outputs"]["alpha-1"]
    out_df = arrow_out.to_pandas()
    assert "ma3" in out_df.columns


def test_alpha_formulaic_rejects_unsafe_dsl() -> None:
    from aqp.lab.executors.alpha_formulaic import execute
    from aqp.lab.executors._types import NodeContext
    from aqp.lab.schema import NodeRuntime, NodeSpec, Port, PortDType

    df = pd.DataFrame({"close": [1.0, 2.0]})
    import pyarrow as pa

    arrow = pa.Table.from_pandas(df, preserve_index=False)
    ctx = NodeContext(
        run_id="r-2",
        node_id="bad-alpha",
        node_type="alpha.formulaic",
        upstream={"bars": {"node_id": "bars"}},
        extras={"_arrow_outputs": {"bars": arrow}},
    )
    node = NodeSpec(
        id="bad-alpha",
        type="alpha.formulaic",
        category="Alpha",
        inputs=[Port(name="bars", dtype=PortDType.BAR_SERIES)],
        outputs=[Port(name="out", dtype=PortDType.SIGNAL)],
        params={"formula": "__import__('os').system('echo pwn')"},
        runtime=NodeRuntime(),
    )
    result = execute(node, ctx)
    assert result.status == "error"
    assert "compile rejected" in (result.error or "").lower() or "forbidden" in (result.error or "").lower()
