"""End-to-end smoke for the analysis layer.

Run via ``python -m scripts.analysis_layer_smoke``. Hermetic: no network,
no Iceberg writes, no DB writes — just import-time sanity + a couple
of flow previews against in-memory frames.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.WARNING)


def main() -> None:
    print("=== analysis package imports ===")
    from aqp.analysis import (
        AnalysisRuntime,
        AnalysisSpec,
        AnalysisStep,
        DatasetRef,
        FLOW_REGISTRY,
        FlowRef,
        list_analysis_flows,
        run_flow,
    )

    flows = list_analysis_flows()
    namespaces = sorted({d.namespace for d in FLOW_REGISTRY.values()})
    print(f"  flows registered: {len(flows)}")
    print(f"  namespaces: {namespaces}")

    print()
    print("=== ORM + persistence ===")
    from aqp.persistence import (
        AnalysisRun as PARun,
        AnalysisSpecRow as PASpec,
        AnalysisSpecVersion as PASpecVer,
        AnalysisStepResult as PAStep,
    )
    from aqp.persistence.models_analysis import (
        AnalysisRun,
        AnalysisSpec as SpecRow,
        AnalysisSpecVersion,
        AnalysisStepResult,
    )

    assert PARun is AnalysisRun
    assert PASpec is SpecRow
    assert PASpecVer is AnalysisSpecVersion
    assert PAStep is AnalysisStepResult
    print("  ORM models export cleanly")

    print()
    print("=== REST router ===")
    from aqp.api.main import app

    analysis_routes = sorted(
        r.path for r in app.router.routes if r.path.startswith("/analysis")
    )
    print(f"  /analysis routes mounted: {len(analysis_routes)}")
    for path in analysis_routes:
        print(f"    {path}")

    print()
    print("=== Celery tasks ===")
    from aqp.tasks.celery_app import celery_app

    analysis_tasks = sorted(
        t for t in celery_app.tasks if "analysis_flow_tasks" in t
    )
    print(f"  analysis-flow tasks: {analysis_tasks}")

    print()
    print("=== sample sync preview (Shapiro-Wilk on synthetic data) ===")
    rng = np.random.default_rng(42)
    df = pd.DataFrame({"x": rng.normal(size=2000)})
    res = run_flow("distribution.shapiro_wilk", df, {"column": "x"})
    pval = res.metrics.get("pvalue")
    is_normal = res.metrics.get("is_normal_05")
    print(f"  pvalue={pval:.4f}  is_normal_05={is_normal}")

    print()
    print("=== sample BSM pricing (no dataset) ===")
    res = run_flow(
        "derivatives.bsm",
        None,
        {
            "spot": 100,
            "strike": 100,
            "rate": 0.05,
            "vol": 0.2,
            "ttm": 1.0,
            "option_type": "call",
        },
    )
    metrics = res.metrics
    print(
        f"  price={metrics['price']:.4f}  delta={metrics['delta']:.4f}  vega={metrics['vega']:.4f}"
    )

    print()
    print("=== AnalysisSpec hash + YAML round-trip ===")
    spec = AnalysisSpec(
        name="smoke",
        dataset=DatasetRef(iceberg_identifier="aqp_silver_yfinance.equities_daily"),
        steps=[
            AnalysisStep(alias="profile", flow_ref=FlowRef(flow="profiling.describe")),
            AnalysisStep(
                alias="dist",
                flow_ref=FlowRef(
                    flow="distribution.descriptive_stats",
                    params={"column": "close"},
                ),
            ),
        ],
    )
    h1 = spec.snapshot_hash()
    spec2 = AnalysisSpec.from_yaml_str(spec.to_yaml())
    print(f"  hash={h1[:16]}  yaml-roundtrip={h1 == spec2.snapshot_hash()}")

    print()
    print("=== AnalysisRuntime.preview (in-memory) ===")
    rt = AnalysisRuntime()
    out = rt.preview("distribution.descriptive_stats", df, {"column": "x"})
    print(
        f"  flow={out.flow}  n={out.metrics.get('n')}  mean={out.metrics.get('mean'):.4f}"
    )

    print()
    print("OK")


if __name__ == "__main__":
    main()
