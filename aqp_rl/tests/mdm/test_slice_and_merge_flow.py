"""``slice_and_merge_regime_flow`` analysis flow tests.

The flow lives in the monolith (:mod:`aqp.analysis.flows.market_dynamics_modeling`)
because per AGENTS rules 23-25 every analysis-flow registration goes
through :class:`AnalysisRuntime`. We test it here from `aqp_rl/tests/`
because the RL framework is its primary consumer.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def trending_price_df() -> pd.DataFrame:
    """Synthetic price series with three regimes — uptrend, sideways, downtrend."""
    rng = np.random.default_rng(0)
    n = 90
    seg1 = 100 + np.linspace(0, 20, 30) + rng.normal(0, 0.5, 30)  # strong uptrend
    seg2 = 120 + rng.normal(0, 0.5, 30)  # sideways
    seg3 = 120 - np.linspace(0, 25, 30) + rng.normal(0, 0.5, 30)  # downtrend
    close = np.concatenate([seg1, seg2, seg3])
    dates = pd.date_range("2020-01-01", periods=n, freq="D").strftime("%Y-%m-%d")
    return pd.DataFrame({"date": dates, "close": close})


def test_flow_importable_and_callable(trending_price_df: pd.DataFrame):
    from aqp.analysis.base import FlowContext
    from aqp.analysis.flows.market_dynamics_modeling import (
        SliceAndMergeRegimeParams,
        slice_and_merge_regime_flow,
    )

    params = SliceAndMergeRegimeParams(
        timestamp_column="date",
        indicator_column="close",
        dynamic_number=3,
        min_length_limit=5,
        labeling_method="quantile",
    )
    ctx = FlowContext(run_id="test", task_id=None)
    result = slice_and_merge_regime_flow(trending_price_df, params, ctx)
    assert result.error is None
    assert result.metrics["n_segments"] > 0
    # Quantile labelling with 3 regimes ⇒ each segment gets a label in {0, 1, 2}.
    rows = result.rows
    assert all(0 <= row["label"] <= 2 for row in rows)


def test_flow_handles_short_data_gracefully():
    from aqp.analysis.base import FlowContext
    from aqp.analysis.flows.market_dynamics_modeling import (
        SliceAndMergeRegimeParams,
        slice_and_merge_regime_flow,
    )

    short = pd.DataFrame({"date": ["2020-01-01"], "close": [100.0]})
    params = SliceAndMergeRegimeParams(min_length_limit=10)
    ctx = FlowContext(run_id="test", task_id=None)
    result = slice_and_merge_regime_flow(short, params, ctx)
    # Either succeeds with zero segments or returns an error — both are acceptable.
    assert result.error is not None or result.metrics.get("n_segments", 0) == 0


def test_flow_groups_by_ticker(trending_price_df: pd.DataFrame):
    """When ``tic_column`` is set, the flow labels each ticker independently."""
    from aqp.analysis.base import FlowContext
    from aqp.analysis.flows.market_dynamics_modeling import (
        SliceAndMergeRegimeParams,
        slice_and_merge_regime_flow,
    )

    # Duplicate the trending series under two tic names.
    a = trending_price_df.assign(tic="A")
    b = trending_price_df.assign(tic="B")
    multi = pd.concat([a, b], ignore_index=True)
    params = SliceAndMergeRegimeParams(
        timestamp_column="date",
        indicator_column="close",
        tic_column="tic",
        dynamic_number=3,
        min_length_limit=5,
    )
    ctx = FlowContext(run_id="test", task_id=None)
    result = slice_and_merge_regime_flow(multi, params, ctx)
    assert result.error is None
    # Both tickers should appear in the rows.
    tics_present = {row.get("tic") for row in result.rows}
    assert tics_present == {"A", "B"}
