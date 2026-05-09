"""Flow registry contract: discovery, lookup, schema export."""
from __future__ import annotations

import pytest

from aqp.analysis import (
    FLOW_REGISTRY,
    FlowParams,
    list_analysis_flows,
    register_analysis_flow,
    resolve_flow,
    run_flow,
)
from aqp.analysis.base import FlowContext, FlowResult


def test_registry_populated() -> None:
    assert len(FLOW_REGISTRY) > 30, "auto-imports should register most flows"


def test_well_known_flows_resolve() -> None:
    for name in (
        "profiling.describe",
        "distribution.shapiro_wilk",
        "outlier.iforest",
        "regression.ols_diagnostics",
        "time_series.adf",
        "derivatives.bsm",
        "portfolio.markowitz_efficient_frontier",
        "factors.evaluate",
    ):
        descriptor = resolve_flow(name)
        assert descriptor.name == name


def test_unknown_flow_raises() -> None:
    with pytest.raises(KeyError):
        resolve_flow("does.not.exist")


def test_schema_includes_params() -> None:
    schemas = list_analysis_flows()
    bsm = next(s for s in schemas if s.name == "derivatives.bsm")
    assert bsm.label == "Black-Scholes-Merton"
    assert "spot" in bsm.params_schema.get("properties", {})
    assert bsm.requires_dataset is False


def test_register_decorator_overrides() -> None:
    class _Params(FlowParams):
        x: int = 0

    @register_analysis_flow(
        name="testing.sentinel",
        namespace="testing",
        label="Sentinel flow",
        description="Fixture flow used by tests.",
        params_model=_Params,
        requires_dataset=False,
    )
    def _runner(df, params, ctx):  # type: ignore[no-redef]
        return FlowResult(flow="testing.sentinel", metrics={"x": int(params.x)})

    out = run_flow("testing.sentinel", None, {"x": 7}, FlowContext())
    assert out.metrics["x"] == 7
