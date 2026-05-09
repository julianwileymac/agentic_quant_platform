"""AnalysisSpec hash invariants — mirrors tests/rl/test_spec.py."""
from __future__ import annotations

import pytest

from aqp.analysis.spec import (
    AnalysisSpec,
    AnalysisStep,
    BusinessMetadataRef,
    DatasetRef,
    FlowRef,
)


def _spec(name: str = "spy-distribution") -> AnalysisSpec:
    return AnalysisSpec(
        name=name,
        description="distribution audit",
        dataset=DatasetRef(iceberg_identifier="aqp_silver_yfinance.equities_daily"),
        steps=[
            AnalysisStep(
                alias="profile",
                flow_ref=FlowRef(flow="profiling.describe", params={}),
            ),
            AnalysisStep(
                alias="shapiro",
                flow_ref=FlowRef(
                    flow="distribution.shapiro_wilk",
                    params={"column": "close"},
                ),
            ),
        ],
        business_metadata=BusinessMetadataRef(
            data_owner="research-team",
            semantic_definition="distribution audit for yfinance equities daily",
            domain="research.distribution",
        ),
    )


def test_hash_is_deterministic() -> None:
    spec_a = _spec()
    spec_b = _spec()
    assert spec_a.snapshot_hash() == spec_b.snapshot_hash()


def test_hash_changes_when_params_change() -> None:
    spec_a = _spec()
    spec_b = _spec()
    spec_b.steps[1].flow_ref.params["column"] = "open"
    assert spec_a.snapshot_hash() != spec_b.snapshot_hash()


def test_hash_changes_when_step_order_changes() -> None:
    spec_a = _spec()
    spec_b = _spec()
    spec_b.steps.reverse()
    assert spec_a.snapshot_hash() != spec_b.snapshot_hash()


def test_yaml_roundtrip_preserves_hash() -> None:
    spec = _spec()
    yaml_form = spec.to_yaml()
    rehydrated = AnalysisSpec.from_yaml_str(yaml_form)
    assert spec.snapshot_hash() == rehydrated.snapshot_hash()


def test_dataset_ref_requires_a_source() -> None:
    with pytest.raises(ValueError):
        DatasetRef()


def test_unique_aliases_enforced() -> None:
    with pytest.raises(ValueError):
        AnalysisSpec(
            name="dup",
            dataset=DatasetRef(iceberg_identifier="aqp_silver_x.t"),
            steps=[
                AnalysisStep(
                    alias="x",
                    flow_ref=FlowRef(flow="profiling.describe"),
                ),
                AnalysisStep(
                    alias="x",
                    flow_ref=FlowRef(flow="profiling.dtypes"),
                ),
            ],
        )


def test_slug_inferred_from_name() -> None:
    spec = _spec("My Analysis")
    assert spec.slug == "my-analysis"


def test_invalid_alias_rejected() -> None:
    with pytest.raises(ValueError):
        AnalysisStep(alias="has space", flow_ref=FlowRef(flow="profiling.describe"))
