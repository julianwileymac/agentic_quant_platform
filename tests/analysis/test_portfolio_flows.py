"""Portfolio flows — synthetic-returns smoke tests."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from aqp.analysis import run_flow


@pytest.fixture
def returns_panel() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    cov = np.array(
        [
            [0.0004, 0.00005, 0.00003],
            [0.00005, 0.0003, 0.00004],
            [0.00003, 0.00004, 0.00025],
        ]
    )
    means = [0.0005, 0.0003, 0.0007]
    n = 500
    rets = rng.multivariate_normal(means, cov, size=n)
    return pd.DataFrame(rets, columns=["A", "B", "C"])


def test_markowitz_returns_frontier(returns_panel: pd.DataFrame) -> None:
    out = run_flow(
        "portfolio.markowitz_efficient_frontier",
        returns_panel,
        {"return_columns": ["A", "B", "C"], "n_points": 7},
    )
    assert out.chart is not None
    assert len(out.rows) >= 1
    # weights should approximately sum to 1
    for r in out.rows:
        weights = [v for k, v in r.items() if k.startswith("w_")]
        assert abs(sum(weights) - 1.0) < 1e-2


def test_ledoit_wolf_returns_psd(returns_panel: pd.DataFrame) -> None:
    out = run_flow(
        "portfolio.ledoit_wolf_shrinkage",
        returns_panel,
        {"return_columns": ["A", "B", "C"]},
    )
    assert out.metrics["n_assets"] == 3
    assert 0 <= out.metrics["shrinkage"] <= 1


def test_risk_parity_weights_positive(returns_panel: pd.DataFrame) -> None:
    out = run_flow(
        "portfolio.risk_parity",
        returns_panel,
        {"return_columns": ["A", "B", "C"]},
    )
    weights = [r["weight"] for r in out.rows]
    assert all(w > 0 for w in weights)
    assert abs(sum(weights) - 1.0) < 1e-3
    rcs = [r["risk_contribution"] for r in out.rows]
    # Each contribution should be close to 1/n
    for rc in rcs:
        assert abs(rc - 1.0 / 3) < 0.05
