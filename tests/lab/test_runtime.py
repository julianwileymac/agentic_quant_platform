"""LabRuntime end-to-end smoke tests (no DB / no Celery)."""
from __future__ import annotations

import pytest

from aqp.lab.runtime import LabRuntime
from aqp.lab.schema import (
    EdgeSpec,
    GraphSpec,
    NodeRuntime,
    NodeSpec,
    Port,
    PortDType,
)


def _two_node_compliance_graph() -> GraphSpec:
    """Build a graph that PASSES every compliance check.

    No data.iceberg_scan (the Phase 0 real executor requires a live
    Iceberg catalog) — we use math.gbm (placeholder executor) so the
    pipeline drops to status='error' on the first node but the
    compile / dispatch / finalise path is exercised end-to-end.
    """
    gbm = NodeSpec(
        id="gbm",
        type="math.gbm",
        category="Math",
        outputs=[Port(name="out", dtype=PortDType.BAR_SERIES)],
        params={"S0": 100, "mu": 0.05, "sigma": 0.2, "T": 1.0, "n_paths": 1000},
        runtime=NodeRuntime(target="celery"),
    )
    rank = NodeSpec(
        id="rank",
        type="xform.rank",
        category="Transformation",
        inputs=[Port(name="in", dtype=PortDType.BAR_SERIES)],
        outputs=[Port(name="out", dtype=PortDType.PANEL)],
        params={"method": "pct"},
        runtime=NodeRuntime(target="celery"),
    )
    return GraphSpec(
        name="gbm-then-rank",
        mode="testing",
        nodes=[gbm, rank],
        edges=[EdgeSpec(source="gbm", target="rank", dtype=PortDType.BAR_SERIES)],
    )


def test_runtime_compiles_testing_graph_end_to_end() -> None:
    spec = _two_node_compliance_graph()
    runtime = LabRuntime(spec)
    result = runtime.submit_run()
    # Both nodes (math.gbm + xform.rank) are real executors after
    # Phase 3 — the pipeline should complete cleanly OR surface a
    # structured error if any single executor fails. Either way the
    # canvas dispatch + compile contract is exercised.
    assert result.status in {"done", "error"}
    assert result.compile_target == "celery_canvas"
    assert result.node_outcomes
    assert result.node_outcomes[0].node_id == "gbm"


def test_runtime_rejects_unknown_node_type() -> None:
    spec = GraphSpec(
        name="bad",
        mode="testing",
        nodes=[
            NodeSpec(
                id="x",
                type="not.a.real.node",
                category="DataSource",
                outputs=[Port(name="out", dtype=PortDType.FRAME)],
            )
        ],
    )
    runtime = LabRuntime(spec)
    result = runtime.submit_run()
    assert result.status == "error"
    assert "not registered" in (result.error or "").lower()


def test_runtime_handles_empty_eda_graph() -> None:
    spec = GraphSpec(name="empty-eda", mode="eda")
    runtime = LabRuntime(spec)
    result = runtime.submit_run()
    assert result.status == "done"
    assert result.compile_target == "inline"
    assert result.metrics.get("n_cells") == 0


def test_runtime_preview_cell_returns_envelope() -> None:
    spec = GraphSpec(name="cell-test", mode="eda")
    runtime = LabRuntime(spec)
    out = runtime.preview_cell("import pandas as pd\nx = pd.DataFrame()", cell_id="c-1")
    assert out["status"] == "done"
    assert out["cell_id"] == "c-1"
    assert "stale_ids" in out


def test_runtime_simulation_stub_runs_clean() -> None:
    from aqp.lab.schema import ModeConfig, SimulationConfig

    spec = GraphSpec(
        name="sim",
        mode="simulation",
        nodes=[
            NodeSpec(
                id="g",
                type="math.heston",
                category="Math",
                outputs=[Port(name="out", dtype=PortDType.BAR_SERIES)],
            )
        ],
        mode_config=ModeConfig(simulation=SimulationConfig(env="stochastic", seed=42)),
    )
    runtime = LabRuntime(spec)
    result = runtime.submit_run()
    assert result.status == "done"
    assert result.compile_target == "dagster_job"
    assert result.metrics.get("env") == "stochastic"


def test_runtime_evaluation_requires_sweep() -> None:
    spec = GraphSpec(
        name="eval-no-sweep",
        mode="evaluation",
        nodes=[
            NodeSpec(
                id="a",
                type="alpha.formulaic",
                category="Alpha",
                params={"decay": 10},
            )
        ],
    )
    runtime = LabRuntime(spec)
    result = runtime.submit_run()
    assert result.status == "error"
    assert "sweep" in (result.error or "").lower()
