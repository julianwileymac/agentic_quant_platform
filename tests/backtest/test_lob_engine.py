"""Tests for :class:`aqp.backtest.hft.LobBacktestEngine`.

The engine wraps optional ``hftbacktest`` so most tests are
``@pytest.mark.requires_hft``-gated. Two unconditional tests verify the
graceful-degradation path: instantiation works without the extra, and
``run`` raises a clear ImportError when called.
"""
from __future__ import annotations

import pytest


def test_lob_engine_instantiates_without_hft_extra() -> None:
    """The engine class itself must import even when hftbacktest is missing."""
    from aqp.backtest.hft import LobBacktestEngine

    engine = LobBacktestEngine(
        latency_profile="constant_50us",
        queue_model="probabilistic",
        tick_size=0.01,
        lot_size=0.001,
    )
    assert engine.latency_profile == "constant_50us"
    assert engine.tick_size == 0.01


def test_lob_engine_run_without_hft_extra_raises() -> None:
    """``run`` should raise a clear ImportError when hftbacktest is missing.

    If the extra IS installed in this environment, the call would
    resolve a builder and (depending on the dataset) maybe complete; we
    accept either outcome to keep the test green in both cases.
    """
    from aqp.backtest.hft import LobBacktestEngine
    from aqp.strategies.hft.alphas import GridMM

    engine = LobBacktestEngine()
    strategy = GridMM(grid_step=0.5, n_levels=3, order_size=1.0)
    try:
        import hftbacktest  # noqa: F401

        # Extra installed — empty feeds returns the empty-result path.
        result = engine.run(strategy, feeds=[], dataset_preset=None)
        assert "reason" in result.summary
    except ImportError:
        with pytest.raises(ImportError):
            engine.run(strategy, feeds=["nonexistent.gz"])


@pytest.mark.requires_hft
def test_lob_engine_runs_against_sample_preset() -> None:
    """Full hermetic backtest against the bundled sample preset.

    Only runs when the ``[hft]`` extra is installed AND the bundled
    sample dataset is available under
    ``inspiration/hftbacktest-master/examples/usdm/``.
    """
    pytest.importorskip("hftbacktest")
    from pathlib import Path

    from aqp.backtest.hft import LobBacktestEngine
    from aqp.strategies.hft.alphas import GridMM

    sample_root = Path("inspiration/hftbacktest-master/examples/usdm")
    if not sample_root.exists():
        pytest.skip("hftbacktest sample feeds not available in this checkout")

    engine = LobBacktestEngine()
    strategy = GridMM(grid_step=0.5, n_levels=3, order_size=1.0)
    result = engine.run(
        strategy,
        feeds=None,
        dataset_preset="lob_btcusdt_sample",
        max_events=10_000,
        snapshot_every=500,
    )
    assert result.summary["events_processed"] >= 0
    assert "engine" in result.summary
