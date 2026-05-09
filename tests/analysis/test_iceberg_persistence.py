"""End-to-end test: AnalysisRuntime persists per-step gold-tier outputs.

The Iceberg writer is monkey-patched to capture every
``append_arrow`` invocation so we can assert:

- one gold-tier write per persistable step;
- the namespace prefix matches ``aqp_gold_analysis_<flow.namespace>``;
- ``medallion_layer="gold"`` is forwarded;
- ``business_metadata`` carries the user-declared metadata.
"""
from __future__ import annotations

from typing import Any

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


def test_runtime_routes_step_outputs_to_iceberg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rng = np.random.default_rng(0)
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=200, freq="D"),
            "ret": rng.normal(loc=0.0, scale=0.01, size=200),
        }
    )

    captured: list[dict[str, Any]] = []

    def fake_append_arrow(identifier, table, **kwargs):  # noqa: ANN001 - test signature
        captured.append(
            {
                "identifier": identifier,
                "rows": table.num_rows if table is not None else 0,
                "kwargs": kwargs,
            }
        )

    class FakeBusinessMetadata:
        def __init__(self, **kw: Any) -> None:
            self.kw = kw

    monkeypatch.setattr(
        "aqp.data.iceberg_catalog.append_arrow", fake_append_arrow
    )
    monkeypatch.setattr(
        "aqp.data.catalog.active_metadata.BusinessMetadata",
        FakeBusinessMetadata,
    )

    spec = AnalysisSpec(
        name="iceberg-test",
        slug="iceberg-test",
        dataset=DatasetRef(iceberg_identifier="ignored.fake"),
        steps=[
            AnalysisStep(
                alias="describe",
                flow_ref=FlowRef(flow="profiling.describe"),
            ),
            AnalysisStep(
                alias="dist",
                flow_ref=FlowRef(
                    flow="distribution.descriptive_stats",
                    params={"column": "ret"},
                ),
            ),
        ],
        business_metadata=BusinessMetadataRef(
            data_owner="research-team",
            semantic_definition="Iceberg roundtrip smoke",
            domain="research.test",
        ),
    )

    rt = AnalysisRuntime(spec)
    monkeypatch.setattr(rt, "_load_dataset", lambda ref: df)
    monkeypatch.setattr(rt, "_snapshot_spec", lambda: (None, None))
    monkeypatch.setattr(rt, "_open_run_row", lambda **kw: None)
    monkeypatch.setattr(rt, "_finalise_run_row", lambda *a, **kw: None)
    monkeypatch.setattr(rt, "_record_step_result", lambda *a, **kw: None)

    result = rt.run()
    assert result.status == "completed"

    # Both flows return arrow data → expect two captured writes.
    assert len(captured) == 2
    namespaces = {entry["identifier"].split(".", 1)[0] for entry in captured}
    assert namespaces == {
        "aqp_gold_analysis_profiling",
        "aqp_gold_analysis_distribution",
    }
    for entry in captured:
        kw = entry["kwargs"]
        assert kw.get("medallion_layer") == "gold"
        assert kw.get("actor", "").startswith("analysis_runtime:")
        assert kw.get("service_name") == "aqp.analysis.runtime"
        bm = kw.get("business_metadata")
        assert bm is not None
        assert bm.kw.get("data_owner") == "research-team"
