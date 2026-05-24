"""GraphSpec / content hashing round-trip tests."""
from __future__ import annotations

import pytest

from aqp.lab.hashing import compute_content_hash, snapshot_data_locator
from aqp.lab.schema import (
    EdgeSpec,
    EvalConfig,
    GraphSpec,
    ModeConfig,
    NodeRuntime,
    NodeSpec,
    Port,
    PortDType,
    SimulationConfig,
    SweepConfig,
)


def _example_testing_graph() -> GraphSpec:
    bars = NodeSpec(
        id="data",
        type="data.iceberg_scan",
        category="DataSource",
        outputs=[Port(name="out", dtype=PortDType.BAR_SERIES)],
        params={
            "namespace": "aqp_silver_equities_bars",
            "table": "bars_1m",
            "snapshot_id": "snap-abc123",
        },
        runtime=NodeRuntime(target="celery", queue="lab.cpu"),
    )
    rank = NodeSpec(
        id="rank",
        type="xform.rank",
        category="Transformation",
        inputs=[Port(name="in", dtype=PortDType.BAR_SERIES)],
        outputs=[Port(name="out", dtype=PortDType.SIGNAL)],
        params={"method": "pct"},
        runtime=NodeRuntime(target="celery"),
    )
    sheet = NodeSpec(
        id="sheet",
        type="out.tearsheet",
        category="Output",
        inputs=[Port(name="in", dtype=PortDType.SIGNAL)],
        params={"benchmark": "SPY"},
        runtime=NodeRuntime(target="celery"),
    )
    return GraphSpec(
        name="echo-graph",
        mode="testing",
        nodes=[bars, rank, sheet],
        edges=[
            EdgeSpec(source="data", target="rank", dtype=PortDType.BAR_SERIES),
            EdgeSpec(source="rank", target="sheet", dtype=PortDType.SIGNAL),
        ],
    )


def test_graph_spec_round_trip() -> None:
    spec = _example_testing_graph()
    dumped = spec.model_dump(mode="json")
    rebuilt = GraphSpec.model_validate(dumped)
    assert rebuilt.snapshot_hash() == spec.snapshot_hash()
    assert compute_content_hash(spec) == compute_content_hash(rebuilt)


def test_topological_sort_is_deterministic() -> None:
    spec = _example_testing_graph()
    order = spec.topological_order()
    assert [n.id for n in order] == ["data", "rank", "sheet"]


def test_topological_sort_rejects_cycles() -> None:
    spec = _example_testing_graph()
    cycled = GraphSpec(
        name="cycle",
        mode="testing",
        nodes=list(spec.nodes),
        edges=[
            *spec.edges,
            EdgeSpec(source="sheet", target="data", dtype=PortDType.SCALAR),
        ],
    )
    with pytest.raises(ValueError):
        cycled.topological_order()


def test_edge_validation_rejects_dangling_endpoints() -> None:
    with pytest.raises(ValueError):
        GraphSpec(
            name="dangling",
            mode="testing",
            nodes=[
                NodeSpec(
                    id="a",
                    type="data.iceberg_scan",
                    category="DataSource",
                    outputs=[Port(name="out", dtype=PortDType.FRAME)],
                )
            ],
            edges=[EdgeSpec(source="a", target="missing")],
        )


def test_mode_config_branch_must_match_mode() -> None:
    with pytest.raises(ValueError):
        GraphSpec(
            name="mismatch",
            mode="eda",
            mode_config=ModeConfig(
                simulation=SimulationConfig(env="hftbt", seed=1)
            ),
        )


def test_eval_sweep_config_serialises() -> None:
    spec = GraphSpec(
        name="sweep",
        mode="evaluation",
        nodes=[
            NodeSpec(
                id="a",
                type="alpha.formulaic",
                category="Alpha",
                params={"decay": 10},
            )
        ],
        mode_config=ModeConfig(
            evaluation=EvalConfig(
                sweep=SweepConfig(
                    algo="optuna_tpe",
                    primary_metric="sharpe",
                    budget=64,
                    cv="combinatorial_purged",
                    cv_kwargs={"n_folds": 6, "n_test_folds": 2},
                    param_paths=["a.decay"],
                    ranges={"a.decay": (5, 30)},
                )
            )
        ),
    )
    json_dump = spec.model_dump(mode="json")
    assert json_dump["mode"] == "evaluation"
    rebuilt = GraphSpec.model_validate(json_dump)
    assert rebuilt.snapshot_hash() == spec.snapshot_hash()


def test_content_hash_is_stable_under_key_order() -> None:
    spec = _example_testing_graph()
    # Same payload, different dict key insertion order, must hash to
    # the same value because canonical JSON sorts keys.
    payload = spec.model_dump(mode="json")
    shuffled = dict(reversed(list(payload.items())))
    assert compute_content_hash(spec) == compute_content_hash(shuffled)


def test_snapshot_data_locator_captures_data_nodes() -> None:
    spec = _example_testing_graph()
    locator = snapshot_data_locator(spec)
    assert "data" in locator
    assert locator["data"]["kind"] == "data.iceberg_scan"
    assert locator["data"]["snapshot_id"] == "snap-abc123"
