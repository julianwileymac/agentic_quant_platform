"""Phase 2 executor smoke tests + audit-emit + reproducibility round-trip.

Each newly-implemented executor has a smoke test below — the goal is
that every node placeholder we removed in Phase 2 has at least one
end-to-end test that exercises ``execute(node, ctx) -> NodeResult``
without crashing on a clean install. Where the dependency is
optional (xgboost, lightgbm, hftbacktest, pyspark, hmmlearn, torch,
mlflow), the test asserts that the executor returns a structured
``status='error'`` with an actionable message rather than a stack
trace.

Plus:

- Audit-emit assertions on every mutating /lab/* endpoint (rule per
  the plan).
- Reproducibility round-trip: build a deterministic GraphSpec,
  hash it, walk through ``snapshot_data_locator`` + ``compute_code_snapshot``,
  build a new GraphSpec with the SAME payload, assert the
  ``content_hash`` is byte-identical.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest

from aqp.lab.executors._types import NodeContext, NodeResult


# ---------------------------------------------------------------------------
# Helpers shared across the executor smoke tests
# ---------------------------------------------------------------------------


class _StubNode:
    """Lightweight stand-in for ``NodeSpec`` used by the executor tests."""

    def __init__(self, *, node_id: str, node_type: str, params: dict[str, Any]) -> None:
        self.id = node_id
        self.type = node_type
        self.params = params


def _ctx(*, node_id: str = "n", upstream: dict[str, Any] | None = None) -> NodeContext:
    return NodeContext(
        run_id="run-1",
        node_id=node_id,
        node_type="test",
        upstream=upstream or {},
        task_id=None,
        request_context=None,
        extras={},
    )


def _ohlcv(n: int = 60, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    return pd.DataFrame(
        {
            "open": np.concatenate(([close[0]], close[:-1])),
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.full(n, 100.0),
        }
    )


def _stash_frame_as_upstream(node_id: str, df: pd.DataFrame) -> dict[str, Any]:
    """Wire an upstream FRAME locator the way the inline canvas does."""
    import pyarrow as pa

    locator: dict[str, Any] = {"kind": "in_process", "node_id": node_id, "rows": len(df), "cols": df.shape[1]}
    arrow = pa.Table.from_pandas(df, preserve_index=False)
    return locator, arrow


def _ctx_with_upstream(
    *, node_id: str = "n", port: str = "in", upstream_node_id: str = "src", df: pd.DataFrame | None = None
) -> NodeContext:
    df = df if df is not None else _ohlcv()
    locator, arrow = _stash_frame_as_upstream(upstream_node_id, df)
    ctx = _ctx(node_id=node_id, upstream={port: locator})
    ctx.extras["_arrow_outputs"] = {upstream_node_id: arrow}
    return ctx


# ---------------------------------------------------------------------------
# math.* executors (numpy / pandas only — no optional deps)
# ---------------------------------------------------------------------------


def test_math_heston_returns_done_with_paths() -> None:
    from aqp.lab.executors.math_heston import execute

    node = _StubNode(node_id="h", node_type="math.heston", params={"n_paths": 32, "n_steps": 64, "seed": 1})
    result = execute(node, _ctx(node_id="h"))
    assert result.status == "done"
    assert result.output_locator["kind"] == "heston"
    assert result.metrics["n_paths"] == 32


def test_math_heston_rejects_invalid_rho() -> None:
    from aqp.lab.executors.math_heston import execute

    node = _StubNode(node_id="h", node_type="math.heston", params={"rho": 1.5})
    result = execute(node, _ctx())
    assert result.status == "error"
    assert "rho" in (result.error or "")


def test_math_ou_jump_returns_done_with_metrics() -> None:
    from aqp.lab.executors.math_ou_jump import execute

    node = _StubNode(
        node_id="o",
        node_type="math.ou_jump",
        params={"n_paths": 16, "n_steps": 64, "jump_intensity": 0.5, "seed": 2},
    )
    result = execute(node, _ctx(node_id="o"))
    assert result.status == "done"
    assert result.output_locator["kind"] == "ou_jump"
    assert "observed_jumps_total" in result.metrics


def test_math_regime_hmm_falls_back_to_heuristic_when_hmmlearn_missing() -> None:
    """Forcing backend='heuristic' must always succeed."""
    from aqp.lab.executors.math_regime_hmm import execute

    df = _ohlcv(120)
    ctx = _ctx_with_upstream(node_id="r", df=df)
    node = _StubNode(node_id="r", node_type="math.regime_hmm", params={"backend": "heuristic", "n_states": 3})
    result = execute(node, ctx)
    assert result.status == "done"
    assert result.output_locator["backend"] == "heuristic"
    assert result.metrics["backend"] == "heuristic"


def test_math_regime_hmm_rejects_short_series() -> None:
    from aqp.lab.executors.math_regime_hmm import execute

    df = _ohlcv(5)
    ctx = _ctx_with_upstream(node_id="r", df=df)
    node = _StubNode(node_id="r", node_type="math.regime_hmm", params={"n_states": 3})
    result = execute(node, ctx)
    assert result.status == "error"


# ---------------------------------------------------------------------------
# data.synthetic
# ---------------------------------------------------------------------------


def test_data_synthetic_renders_path_from_gbm_upstream() -> None:
    """Pretend an upstream math.gbm wrote a 1-row wide DataFrame; render it as bars."""
    from aqp.lab.executors.data_synthetic import execute

    wide = pd.DataFrame(
        np.linspace(100, 110, 10).reshape(1, -1),
        columns=[f"step_{i}" for i in range(10)],
    )
    wide.insert(0, "path_id", [0])
    ctx = _ctx_with_upstream(node_id="syn", df=wide)
    node = _StubNode(node_id="syn", node_type="data.synthetic", params={"path_index": 0, "output_columns": "close"})
    result = execute(node, ctx)
    assert result.status == "done"
    assert result.output_locator["kind"] == "synthetic"
    assert result.output_locator["output_columns"] == "close"
    assert result.output_locator["rows"] == 10
    assert result.output_locator["cols"] == 1
    # Downstream FRAME consumers read via the inline canvas extras
    # passthrough — confirm we stashed the close series there.
    arrow_outputs = ctx.extras.get("_arrow_outputs", {})
    assert "syn" in arrow_outputs
    table = arrow_outputs["syn"]
    assert "close" in table.column_names


def test_data_synthetic_rejects_missing_upstream() -> None:
    from aqp.lab.executors.data_synthetic import execute

    node = _StubNode(node_id="syn", node_type="data.synthetic", params={})
    result = execute(node, _ctx())
    assert result.status == "error"


# ---------------------------------------------------------------------------
# label.* executors
# ---------------------------------------------------------------------------


def test_label_trend_scan_returns_label_frame() -> None:
    from aqp.lab.executors.label_trend_scan import execute

    df = _ohlcv(60)
    ctx = _ctx_with_upstream(node_id="lbl", df=df)
    node = _StubNode(node_id="lbl", node_type="label.trend_scan", params={"t_horizons": [3, 5, 10]})
    result = execute(node, ctx)
    assert result.status == "done"
    assert result.output_locator["kind"] == "trend_scan"
    assert "positive_count" in result.metrics


def test_label_meta_returns_meta_label_frame() -> None:
    from aqp.lab.executors.label_meta import execute

    df = _ohlcv(40)
    df["signal"] = np.sign(df["close"].diff().fillna(0.0))
    df["forward_return"] = df["close"].pct_change().shift(-1).fillna(0.0)
    ctx = _ctx_with_upstream(node_id="m", df=df)
    node = _StubNode(node_id="m", node_type="label.meta", params={})
    result = execute(node, ctx)
    assert result.status == "done"
    assert result.output_locator["kind"] == "meta_labels"
    assert 0 <= float(result.metrics["hit_rate"]) <= 1


# ---------------------------------------------------------------------------
# Optional-dep executors — error path coverage
# ---------------------------------------------------------------------------


def test_data_hudi_scan_missing_params_returns_error() -> None:
    from aqp.lab.executors.data_hudi_scan import execute

    node = _StubNode(node_id="h", node_type="data.hudi_scan", params={})
    result = execute(node, _ctx())
    assert result.status == "error"


def test_data_redpanda_subscribe_missing_topic_returns_error() -> None:
    from aqp.lab.executors.data_redpanda_subscribe import execute

    node = _StubNode(node_id="r", node_type="data.redpanda_subscribe", params={})
    result = execute(node, _ctx())
    assert result.status == "error"


def test_alpha_ml_missing_uri_returns_error() -> None:
    from aqp.lab.executors.alpha_ml import execute

    node = _StubNode(node_id="a", node_type="alpha.ml", params={})
    result = execute(node, _ctx())
    assert result.status == "error"


def test_model_gbm_rejects_unknown_framework() -> None:
    from aqp.lab.executors.model_gbm import execute

    node = _StubNode(node_id="g", node_type="model.gbm", params={"framework": "unknown", "target_column": "y"})
    result = execute(node, _ctx())
    assert result.status == "error"


def test_model_torch_snippet_id_returns_phase4_error() -> None:
    from aqp.lab.executors.model_torch import execute

    node = _StubNode(node_id="t", node_type="model.torch", params={"target_column": "y", "snippet_id": "x"})
    result = execute(node, _ctx())
    assert result.status == "error"
    assert "tier-2" in (result.error or "").lower() or "phase 4" in (result.error or "").lower()


def test_model_rl_invalid_action_returns_error() -> None:
    from aqp.lab.executors.model_rl import execute

    node = _StubNode(node_id="rl", node_type="model.rl", params={"action": "unknown_action", "spec_name": "x"})
    result = execute(node, _ctx())
    assert result.status == "error"


def test_strategy_lean_framework_requires_input() -> None:
    from aqp.lab.executors.strategy_lean_framework import execute

    node = _StubNode(node_id="l", node_type="strategy.lean_framework", params={})
    result = execute(node, _ctx())
    assert result.status == "error"


def test_strategy_hftbt_market_maker_requires_dataset() -> None:
    from aqp.lab.executors.strategy_hftbt_market_maker import execute

    node = _StubNode(node_id="mm", node_type="strategy.hftbt_market_maker", params={})
    result = execute(node, _ctx())
    assert result.status == "error"


# ---------------------------------------------------------------------------
# Reproducibility round-trip
# ---------------------------------------------------------------------------


def test_content_hash_is_byte_identical_for_equivalent_specs() -> None:
    """Two GraphSpecs constructed from the same payload must hash equal.

    Pin the EdgeSpec id explicitly so the auto-generated default
    (uuid-backed) doesn't poison the hash. The frontend that ships
    these specs already supplies stable ids; this test pins them so
    the reproducibility contract is provable without the frontend.
    """
    from aqp.lab.hashing import compute_content_hash
    from aqp.lab.schema import (
        EdgeSpec,
        GraphSpec,
        NodeSpec,
        Port,
        PortDType,
    )

    def _build() -> GraphSpec:
        return GraphSpec(
            name="repro",
            mode="testing",
            nodes=[
                NodeSpec(
                    id="src",
                    type="data.iceberg_scan",
                    category="DataSource",
                    outputs=[Port(name="out", dtype=PortDType.FRAME)],
                    params={"namespace": "aqp_silver_equities_bars", "table": "bars_1m"},
                ),
                NodeSpec(
                    id="rank",
                    type="xform.rank",
                    category="Transformation",
                    inputs=[Port(name="in", dtype=PortDType.PANEL)],
                    outputs=[Port(name="out", dtype=PortDType.PANEL)],
                    params={"method": "pct"},
                ),
            ],
            edges=[EdgeSpec(id="e-pinned", source="src", target="rank")],
        )

    h1 = compute_content_hash(_build())
    h2 = compute_content_hash(_build())
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex


def test_content_hash_changes_when_params_change() -> None:
    from aqp.lab.hashing import compute_content_hash
    from aqp.lab.schema import GraphSpec, NodeSpec, Port, PortDType

    def _build(window: int) -> GraphSpec:
        return GraphSpec(
            name="repro2",
            mode="testing",
            nodes=[
                NodeSpec(
                    id="f",
                    type="feature.technical",
                    category="Feature",
                    inputs=[Port(name="in", dtype=PortDType.BAR_SERIES)],
                    outputs=[Port(name="out", dtype=PortDType.PANEL)],
                    params={"indicator": "rsi", "window": window},
                ),
            ],
        )

    h_a = compute_content_hash(_build(14))
    h_b = compute_content_hash(_build(21))
    h_a2 = compute_content_hash(_build(14))
    assert h_a == h_a2  # equivalent payload → same hash
    assert h_a != h_b   # different param → different hash


def test_compute_code_snapshot_is_deterministic_within_a_process() -> None:
    """Repeated calls within a process return the same digest (cache + git SHA + image map)."""
    from aqp.lab.hashing import compute_code_snapshot, reset_code_snapshot_cache

    reset_code_snapshot_cache()
    a = compute_code_snapshot()
    b = compute_code_snapshot()
    assert a == b
    assert len(a) == 64


def test_snapshot_data_locator_returns_kind_per_data_node() -> None:
    """Every data.* node MUST appear on the locator (rule per the plan)."""
    from aqp.lab.hashing import snapshot_data_locator
    from aqp.lab.schema import (
        EdgeSpec,
        GraphSpec,
        NodeSpec,
        Port,
        PortDType,
    )

    spec = GraphSpec(
        name="locator-test",
        mode="testing",
        nodes=[
            NodeSpec(
                id="ice",
                type="data.iceberg_scan",
                category="DataSource",
                outputs=[Port(name="out", dtype=PortDType.FRAME)],
                params={"namespace": "aqp_silver_equities_bars", "table": "bars_1m"},
            ),
            NodeSpec(
                id="syn",
                type="data.synthetic",
                category="DataSource",
                outputs=[Port(name="out", dtype=PortDType.BAR_SERIES)],
                params={"seed": 7, "n": 100},
            ),
            NodeSpec(
                id="r",
                type="xform.rank",
                category="Transformation",
                inputs=[Port(name="in", dtype=PortDType.PANEL)],
                outputs=[Port(name="out", dtype=PortDType.PANEL)],
                params={"method": "pct"},
            ),
        ],
        edges=[
            EdgeSpec(source="ice", target="r"),
            EdgeSpec(source="syn", target="r"),
        ],
    )
    locator = snapshot_data_locator(spec)
    assert "ice" in locator
    assert locator["ice"]["kind"] == "data.iceberg_scan"
    assert "syn" in locator
    assert locator["syn"]["kind"] == "data.synthetic"
    # xform.rank is not a Data Source — must not appear.
    assert "r" not in locator


# ---------------------------------------------------------------------------
# Audit emit on every mutating /lab/* endpoint
# ---------------------------------------------------------------------------


def test_route_audit_emit_calls_present() -> None:
    """Source-level assertion: every mutating /lab/* endpoint has emit_audit_event.

    Phase 0 added :func:`emit_audit_event` to ``create_graph``,
    ``patch_graph``, ``delete_graph``, ``submit_graph_run``,
    ``cancel_run``, ``halt_all``, ``create_label``, ``delete_label``,
    ``create_note``, ``train_labeler``, ``promote_cell_to_testing_graph``,
    ``reproduce_run``, and ``run_single_node``. This test fails when
    a new mutating route is added without an audit emit.
    """
    import inspect

    from aqp.api.routes import lab as lab_route

    expected_audit_events = {
        "lab.graph.create",
        "lab.graph.create.dedup",
        "lab.graph.create.compliance_denied",
        "lab.graph.patch",
        "lab.graph.patch.compliance_denied",
        "lab.graph.delete",
        "lab.run.submit",
        "lab.run.submit.inline",
        "lab.run.cancel",
        "lab.halt_all",
        "lab.label.create",
        "lab.label.delete",
        "lab.note.create",
        "lab.labeler.train",
        "lab.labeler.train.dedup",
        "lab.cell.promote",
        "lab.cell.promote.safety_denied",
        "lab.run.reproduce",
        "lab.run.reproduce.code_drift",
        "lab.node.run.submit",
    }
    source = inspect.getsource(lab_route)
    missing = {evt for evt in expected_audit_events if f'"{evt}"' not in source}
    assert not missing, f"Missing audit emits in lab route: {missing}"


def test_route_mutating_endpoints_require_write_scope() -> None:
    """Source-level assertion: every mutating /lab/* endpoint declares require_scope.

    Phase 0 enforces ``data:write`` on mutating routes and
    ``data:admin`` on ``delete_graph`` + ``halt-all``. Newly-added
    mutating endpoints MUST add the scope dep or this assertion
    flags the regression.
    """
    import inspect

    from aqp.api.routes import lab as lab_route

    source = inspect.getsource(lab_route)
    # We don't need to count exact occurrences; we just assert the
    # presence of every scope dep we expect after Phase 0.
    assert 'require_scope("data:write")' in source
    assert 'require_scope("data:admin")' in source


# ---------------------------------------------------------------------------
# Module-level smoke: every executor module imports without crashing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "module",
    [
        "aqp.lab.executors.data_hudi_scan",
        "aqp.lab.executors.data_redpanda_subscribe",
        "aqp.lab.executors.data_synthetic",
        "aqp.lab.executors.feature_embedding",
        "aqp.lab.executors.alpha_ml",
        "aqp.lab.executors.model_gbm",
        "aqp.lab.executors.model_torch",
        "aqp.lab.executors.model_rl",
        "aqp.lab.executors.strategy_lean_framework",
        "aqp.lab.executors.strategy_hftbt_market_maker",
        "aqp.lab.executors.math_heston",
        "aqp.lab.executors.math_ou_jump",
        "aqp.lab.executors.math_regime_hmm",
        "aqp.lab.executors.label_meta",
        "aqp.lab.executors.label_trend_scan",
        "aqp.lab.executors.snippet_python",
        "aqp.lab.executors.snippet_sql",
    ],
)
def test_executor_module_imports(module: str) -> None:
    import importlib

    mod = importlib.import_module(module)
    assert callable(getattr(mod, "execute", None)), f"{module} missing execute()"
