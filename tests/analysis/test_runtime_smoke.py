"""End-to-end :class:`AnalysisRuntime` smoke tests.

The Iceberg writer is monkey-patched to a no-op so the test stays
hermetic; the goal is to exercise the *runtime lifecycle* (spec
snapshot, run row, step-result row, progress emission) without
spinning up PyIceberg or the docker stack.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from aqp.analysis.runtime import AnalysisRuntime
from aqp.analysis.spec import (
    AnalysisSpec,
    AnalysisStep,
    BusinessMetadataRef,
    DatasetRef,
    FlowRef,
)


@pytest.fixture
def synthetic_frame() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=500, freq="D"),
            "vt_symbol": ["SPY.NYSE"] * 500,
            "close": rng.normal(loc=400, scale=5, size=500),
        }
    )
    df["log_return"] = np.log(df["close"] / df["close"].shift(1)).fillna(0.0)
    return df


def _make_spec() -> AnalysisSpec:
    return AnalysisSpec(
        name="smoke-test",
        slug="smoke-test",
        dataset=DatasetRef(iceberg_identifier="ignored.fake"),
        steps=[
            AnalysisStep(
                alias="describe",
                flow_ref=FlowRef(flow="profiling.describe", params={}),
            ),
            AnalysisStep(
                alias="dist",
                flow_ref=FlowRef(
                    flow="distribution.descriptive_stats",
                    params={"column": "log_return"},
                ),
            ),
            AnalysisStep(
                alias="zscore",
                flow_ref=FlowRef(
                    flow="outlier.zscore",
                    params={"column": "log_return", "threshold": 3.0},
                ),
            ),
        ],
        business_metadata=BusinessMetadataRef(
            data_owner="research-team",
            semantic_definition="smoke-test fixture",
            domain="research.smoke",
        ),
    )


def test_runtime_run_completes(
    synthetic_frame: pd.DataFrame, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = _make_spec()
    rt = AnalysisRuntime(spec)
    # Short-circuit dataset loading and Iceberg persistence.
    monkeypatch.setattr(rt, "_load_dataset", lambda ref: synthetic_frame)
    monkeypatch.setattr(rt, "_maybe_persist_arrow", lambda **kw: None)
    monkeypatch.setattr(rt, "_snapshot_spec", lambda: (None, None))
    monkeypatch.setattr(rt, "_open_run_row", lambda **kw: None)
    monkeypatch.setattr(rt, "_finalise_run_row", lambda *a, **kw: None)
    monkeypatch.setattr(rt, "_record_step_result", lambda *a, **kw: None)

    result = rt.run()
    assert result.status == "completed"
    assert {s.alias for s in result.steps} == {"describe", "dist", "zscore"}
    assert all(s.status == "completed" for s in result.steps)
    descriptive = next(s for s in result.steps if s.alias == "dist")
    assert "mean" in descriptive.metrics
    assert "std" in descriptive.metrics


def test_runtime_preview_one_shot(synthetic_frame: pd.DataFrame) -> None:
    rt = AnalysisRuntime()
    result = rt.preview(
        "distribution.shapiro_wilk",
        synthetic_frame,
        {"column": "log_return"},
    )
    assert result.flow == "distribution.shapiro_wilk"
    assert "pvalue" in result.metrics


def test_runtime_unknown_flow_recorded_as_error(
    synthetic_frame: pd.DataFrame, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = AnalysisSpec(
        name="bad",
        slug="bad",
        dataset=DatasetRef(iceberg_identifier="ignored.fake"),
        steps=[
            AnalysisStep(
                alias="ghost",
                flow_ref=FlowRef(flow="does.not.exist", params={}),
            ),
        ],
        business_metadata=BusinessMetadataRef(
            data_owner="t",
            semantic_definition="t",
        ),
    )
    rt = AnalysisRuntime(spec)
    monkeypatch.setattr(rt, "_load_dataset", lambda ref: synthetic_frame)
    monkeypatch.setattr(rt, "_maybe_persist_arrow", lambda **kw: None)
    monkeypatch.setattr(rt, "_snapshot_spec", lambda: (None, None))
    monkeypatch.setattr(rt, "_open_run_row", lambda **kw: None)
    monkeypatch.setattr(rt, "_finalise_run_row", lambda *a, **kw: None)
    monkeypatch.setattr(rt, "_record_step_result", lambda *a, **kw: None)
    result = rt.run()
    assert result.status == "error"
    assert result.steps[0].status == "error"
    assert "does.not.exist" in (result.steps[0].error or "")
