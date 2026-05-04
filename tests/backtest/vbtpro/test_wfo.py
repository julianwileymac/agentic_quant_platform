"""WalkForwardHarness tests — skipped when vbt-pro absent."""
from __future__ import annotations

import pandas as pd
import pytest

vbt = pytest.importorskip("vectorbtpro")


def test_wfo_harness_n_windows(synthetic_bars: pd.DataFrame) -> None:
    from aqp.backtest.vbtpro.wfo import WalkForwardHarness

    harness = WalkForwardHarness(
        strategy_cfg={
            "class": "SmaCross",
            "module_path": "aqp.strategies.examples.sma_cross",
            "kwargs": {"fast": 5, "slow": 20, "allow_short": False},
        },
        splitter="rolling",
        n_splits=3,
        engine_kwargs={"mode": "signals", "initial_cash": 100_000.0, "warmup_bars": 5},
    )
    result = harness.run(synthetic_bars)
    assert len(result.windows) > 0
    assert len(result.windows) <= 3
    assert result.summary.get("engine") == "vectorbt-pro"
    assert result.summary.get("mode") == "walk_forward"


def test_wfo_stitched_equity_monotonic_index(synthetic_bars: pd.DataFrame) -> None:
    from aqp.backtest.vbtpro.wfo import WalkForwardHarness

    harness = WalkForwardHarness(
        strategy_cfg={
            "class": "SmaCross",
            "module_path": "aqp.strategies.examples.sma_cross",
            "kwargs": {"fast": 5, "slow": 20, "allow_short": False},
        },
        splitter="rolling",
        n_splits=3,
        engine_kwargs={"mode": "signals", "initial_cash": 100_000.0, "warmup_bars": 5},
    )
    result = harness.run(synthetic_bars)
    # Equity may be empty in degenerate splits; only check monotonic when present.
    if len(result.stitched_equity) > 1:
        assert result.stitched_equity.index.is_monotonic_increasing
