"""Hermetic tests for the FinRL-X weight-centric pipeline."""
from __future__ import annotations

import numpy as np

from aqp_rl.portfolio import (
    GrossExposureRiskOverlay,
    IdentityAllocator,
    PositionCapRiskOverlay,
    StackedRiskOverlay,
    StaticUniverseSelector,
    TurbulenceTimingAdjuster,
    WeightCentricPipeline,
)


def test_pipeline_records_all_four_stages():
    pipeline = WeightCentricPipeline(
        selector=StaticUniverseSelector(universe=["A", "B", "C"]),
        allocator=IdentityAllocator(),
        timing=TurbulenceTimingAdjuster(threshold=80.0, cooldown_scale=0.5),
        risk_overlay=PositionCapRiskOverlay(max_position_pct=0.5),
    )
    state = pipeline.run(
        universe=["A", "B", "C"],
        raw_action=np.array([0.4, 0.3, 0.3]),
        context={"turbulence": 50.0},
    )
    stages = [name for name, _ in state.history]
    assert stages == ["f_S", "f_A", "f_T", "f_R"]


def test_turbulence_timing_cuts_exposure_above_threshold():
    pipeline = WeightCentricPipeline(
        selector=StaticUniverseSelector(universe=["X"]),
        allocator=IdentityAllocator(),
        timing=TurbulenceTimingAdjuster(threshold=100.0, cooldown_scale=0.0),
        risk_overlay=GrossExposureRiskOverlay(max_gross=10.0),
    )
    state_low = pipeline.run(universe=["X"], raw_action=[0.5], context={"turbulence": 50.0})
    state_high = pipeline.run(universe=["X"], raw_action=[0.5], context={"turbulence": 200.0})
    assert state_low.weights[0] == 0.5
    assert state_high.weights[0] == 0.0


def test_position_cap_marks_truncated_when_breach():
    pipeline = WeightCentricPipeline(
        selector=StaticUniverseSelector(universe=["A", "B"]),
        allocator=IdentityAllocator(),
        risk_overlay=PositionCapRiskOverlay(max_position_pct=0.20, mark_truncated=True),
    )
    state = pipeline.run(
        universe=["A", "B"],
        raw_action=np.array([0.5, 0.1]),
        context={},
    )
    assert state.context.get("truncated") is True
    assert state.weights[0] <= 0.20 + 1e-9
    assert state.weights[1] <= 0.20 + 1e-9


def test_gross_exposure_scales_when_over_budget():
    pipeline = WeightCentricPipeline(
        selector=StaticUniverseSelector(universe=["A", "B", "C"]),
        allocator=IdentityAllocator(),
        risk_overlay=GrossExposureRiskOverlay(max_gross=1.0),
    )
    state = pipeline.run(
        universe=["A", "B", "C"],
        raw_action=np.array([1.0, 1.0, 1.0]),
        context={},
    )
    assert abs(np.abs(state.weights).sum() - 1.0) < 1e-9


def test_stacked_overlay_chains_position_cap_then_gross():
    pipeline = WeightCentricPipeline(
        selector=StaticUniverseSelector(universe=["A", "B"]),
        allocator=IdentityAllocator(),
        risk_overlay=StackedRiskOverlay(overlays=[
            PositionCapRiskOverlay(max_position_pct=0.4),
            GrossExposureRiskOverlay(max_gross=0.6),
        ]),
    )
    state = pipeline.run(
        universe=["A", "B"],
        raw_action=np.array([0.9, 0.9]),
        context={},
    )
    assert max(state.weights) <= 0.4
    assert abs(state.weights).sum() <= 0.6 + 1e-9


def test_history_preserved_across_stages():
    pipeline = WeightCentricPipeline(
        selector=StaticUniverseSelector(universe=["A", "B"]),
        allocator=IdentityAllocator(),
        timing=TurbulenceTimingAdjuster(threshold=200.0, scale=0.5),
        risk_overlay=PositionCapRiskOverlay(max_position_pct=0.25),
    )
    state = pipeline.run(
        universe=["A", "B"],
        raw_action=np.array([1.0, 1.0]),
        context={"turbulence": 50.0},
    )
    f_a = next(vec for name, vec in state.history if name == "f_A")
    f_t = next(vec for name, vec in state.history if name == "f_T")
    f_r = next(vec for name, vec in state.history if name == "f_R")
    # f_A: raw weights, f_T: scaled by 0.5, f_R: clipped to 0.25
    assert np.allclose(f_a, [1.0, 1.0])
    assert np.allclose(f_t, [0.5, 0.5])
    assert np.allclose(f_r, [0.25, 0.25])
