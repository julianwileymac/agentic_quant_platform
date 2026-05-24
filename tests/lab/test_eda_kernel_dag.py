"""Phase 1 EDA kernel DAG + snippet executor tests.

Extends :mod:`tests.lab.test_eda_kernel` with the following Phase 1
coverage:

- Stale-DAG propagation when a cell's defines / references change.
- AST-rejection of the full forbidden vocabulary
  (``os.system``/``subprocess``/``eval``/``exec``/``__import__``).
- The :mod:`aqp.lab.executors.snippet_python` Phase 1 in-process Tier-1
  executor returns ``status='done'`` for safe code, error for unsafe
  code, and preserves repr/stdout/stderr.
- Stdout/stderr/repr capture under the 5s SLA the plan specifies
  (we cap to 1s in tests to keep CI fast).

The cell-promote endpoint integration lives in
:mod:`tests.api.test_lab_routes` (audit + scope coverage); this file
focuses on the kernel / DAG / snippet executor without HTTP boundaries.
"""
from __future__ import annotations

import time

import pytest

from aqp.lab.eda import EdaKernel, analyse_cell_dependencies
from aqp.lab.eda.cell_dag import (
    CellNode,
    build_cell_graph,
    stale_descendants_of,
)
from aqp.lab.eda.kernel import CellSafetyError, _ast_safety_check
from aqp.lab.executors._types import NodeContext
from aqp.lab.executors.snippet_python import execute as snippet_python_execute
from aqp.lab.registry import (
    NODE_TYPES,
    get_node_type,
    known_aliases,
    resolve_executor,
)


# ---------------------------------------------------------------------------
# Stale-DAG propagation when defines / references change
# ---------------------------------------------------------------------------


def test_stale_propagation_when_definer_source_changes() -> None:
    """Editing the source of an upstream cell marks every downstream stale."""
    kernel = EdaKernel("test-stale-1")
    kernel.execute_cell("a", "shared = 1")
    kernel.execute_cell("b", "double = shared * 2")
    kernel.execute_cell("c", "triple = shared * 3")

    snapshot = kernel.graph_snapshot()
    by_id = snapshot.index()
    assert by_id["b"].stale is False
    assert by_id["c"].stale is False

    kernel.upsert_cell("a", "shared = 99")
    snapshot = kernel.graph_snapshot()
    by_id = snapshot.index()
    assert by_id["b"].stale is True
    assert by_id["c"].stale is True


def test_stale_propagation_transitive_across_three_layers() -> None:
    cells = [
        CellNode(id="a", source="base = 1", ord=0),
        CellNode(id="b", source="mid = base + 1", ord=1),
        CellNode(id="c", source="leaf = mid * 2", ord=2),
    ]
    graph = build_cell_graph(cells)
    stale = stale_descendants_of(graph, "a")
    assert {"b", "c"} <= set(stale)


def test_stale_propagation_drops_after_rebind_of_intermediate() -> None:
    """When ``b`` no longer references ``a``, editing ``a`` leaves ``b`` stable."""
    cells = [
        CellNode(id="a", source="shared = 1", ord=0),
        CellNode(id="b", source="shared = 42  # rebinds locally", ord=1),
        CellNode(id="c", source="leaf = shared", ord=2),
    ]
    graph = build_cell_graph(cells)
    stale = stale_descendants_of(graph, "a")
    # ``c`` reads ``shared`` which is most-recently defined by ``b``,
    # NOT ``a``. Editing ``a`` therefore does not invalidate ``c``.
    assert "c" not in stale


def test_stale_propagation_handles_added_reference() -> None:
    """Adding a NEW reference in ``b`` connects to ``a`` on the next analysis."""
    cells = [
        CellNode(id="a", source="upstream_value = 42", ord=0),
        CellNode(id="b", source="x = 1", ord=1),
    ]
    graph = build_cell_graph(cells)
    assert stale_descendants_of(graph, "a") == []

    cells[1].source = "x = upstream_value + 1"
    graph = build_cell_graph(cells)
    assert "b" in stale_descendants_of(graph, "a")


# ---------------------------------------------------------------------------
# AST safety guard — full forbidden vocabulary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "snippet",
    [
        "import os\nos.system('echo pwned')",
        "import subprocess\nsubprocess.run(['ls'])",
        "from subprocess import Popen\nPopen(['ls'])",
        "eval('1 + 1')",
        "exec('print(1)')",
        "__import__('ctypes')",
        "from ctypes import c_int",
        "open('/etc/passwd').read()",
    ],
)
def test_safety_guard_rejects_forbidden_call(snippet: str) -> None:
    with pytest.raises(CellSafetyError):
        _ast_safety_check(snippet)


@pytest.mark.parametrize(
    "snippet",
    [
        "import pandas as pd",
        "import numpy as np",
        "df = pd.DataFrame({'x':[1,2,3]})",
        "result = sum(range(10))",
        "for i in range(10): pass",
        "class Foo:\n    pass\n",
    ],
)
def test_safety_guard_allows_safe_python(snippet: str) -> None:
    # No exception expected.
    _ast_safety_check(snippet)


# ---------------------------------------------------------------------------
# snippet.python Tier 1 executor
# ---------------------------------------------------------------------------


def _make_ctx(node_id: str = "snip-1") -> NodeContext:
    return NodeContext(
        run_id="run-1",
        node_id=node_id,
        node_type="snippet.python",
        upstream={},
        task_id=None,
        request_context=None,
        extras={},
    )


class _Node:
    def __init__(self, params: dict) -> None:
        self.params = params
        self.type = "snippet.python"
        self.id = "snip"


def test_snippet_python_tier1_runs_safe_source() -> None:
    node = _Node({"source": "x = 7\ny = x * 6\ny", "tier": "tier1"})
    ctx = _make_ctx()
    result = snippet_python_execute(node, ctx)
    assert result.status == "done"
    assert result.output_locator["kind"] == "snippet_inline"
    assert result.output_locator["tier"] == "tier1"
    assert "42" in (result.output_locator.get("value_repr") or "")


def test_snippet_python_tier1_rejects_unsafe_source() -> None:
    node = _Node({"source": "import subprocess\nsubprocess.run(['ls'])", "tier": "tier1"})
    ctx = _make_ctx()
    result = snippet_python_execute(node, ctx)
    assert result.status == "error"
    assert "forbidden" in (result.error or "").lower() or "safety" in (result.error or "").lower()


def test_snippet_python_tier1_captures_stdout() -> None:
    node = _Node({"source": "print('hello-from-snippet')\n", "tier": "tier1"})
    ctx = _make_ctx()
    result = snippet_python_execute(node, ctx)
    assert result.status == "done"
    # stdout text is captured inside the output_locator for the
    # run-history drawer.
    assert "hello-from-snippet" in (result.output_locator.get("stdout") or "")


def test_snippet_python_tier1_surfaces_primary_output() -> None:
    """Binding ``out`` in the snippet body promotes it to the extras passthrough."""
    node = _Node(
        {
            "source": "import pandas as pd\nout = pd.DataFrame({'a':[1,2,3]})\nout",
            "tier": "tier1",
        }
    )
    ctx = _make_ctx()
    result = snippet_python_execute(node, ctx)
    assert result.status == "done"
    assert result.output_locator.get("primary_in_extras") is True
    snippet_outputs = ctx.extras.get("snippet_outputs", {})
    assert "snip-1" in snippet_outputs
    primary = snippet_outputs["snip-1"]
    assert hasattr(primary, "columns")


def test_snippet_python_missing_source_returns_error() -> None:
    node = _Node({})
    ctx = _make_ctx()
    result = snippet_python_execute(node, ctx)
    assert result.status == "error"
    assert "source" in (result.error or "").lower()


def test_snippet_python_tier2_phase4_placeholder() -> None:
    """Tier 2 is a Phase 4 placeholder — returns a structured error today."""
    node = _Node({"source": "x = 1", "tier": "tier2"})
    ctx = _make_ctx()
    result = snippet_python_execute(node, ctx)
    assert result.status == "error"
    assert "tier2" in (result.error or "").lower() or "phase 4" in (result.error or "").lower()


# ---------------------------------------------------------------------------
# Stdout/stderr/repr SLA timing
# ---------------------------------------------------------------------------


def test_kernel_execute_cell_under_one_second_sla() -> None:
    """The kernel must capture a simple cell under 1s (plan §1 5s budget)."""
    kernel = EdaKernel("test-sla")
    start = time.perf_counter()
    result = kernel.execute_cell("a", "x = sum(range(1000))\nx")
    duration_ms = (time.perf_counter() - start) * 1000.0
    assert result.status == "done"
    assert result.repr_value is not None
    # Tighter than the 5s plan SLA to catch perf regressions early.
    assert duration_ms < 1000.0, f"execute_cell took {duration_ms:.1f}ms (>1000ms budget)"


# ---------------------------------------------------------------------------
# Snippet node type registry shape
# ---------------------------------------------------------------------------


def test_snippet_node_types_registered() -> None:
    aliases = known_aliases()
    assert "snippet.python" in aliases
    assert "snippet.sql" in aliases


def test_snippet_node_types_have_executors() -> None:
    py = get_node_type("snippet.python")
    sql = get_node_type("snippet.sql")
    # The executor strings must resolve to a callable.
    py_fn = resolve_executor(py.alias)
    sql_fn = resolve_executor(sql.alias)
    assert callable(py_fn)
    assert callable(sql_fn)


def test_node_taxonomy_grew_to_37_with_snippet_additions() -> None:
    """Phase 1 added snippet.python + snippet.sql on top of the 35-node taxonomy."""
    assert len(NODE_TYPES) == 37


# ---------------------------------------------------------------------------
# Dependency analysis edge cases the existing kernel tests don't cover
# ---------------------------------------------------------------------------


def test_dependency_analysis_handles_tuple_unpacking() -> None:
    deps = analyse_cell_dependencies("c1", "a, b = upstream_pair")
    assert "a" in deps.defines
    assert "b" in deps.defines
    assert "upstream_pair" in deps.references


def test_dependency_analysis_handles_augmented_assign() -> None:
    deps = analyse_cell_dependencies("c1", "counter += 1")
    # AugAssign both reads and writes the target — recorded as both.
    assert "counter" in deps.defines


def test_dependency_analysis_handles_comprehension_targets() -> None:
    """Comprehension-local targets should NOT appear in cell-level defines."""
    deps = analyse_cell_dependencies(
        "c1",
        "doubled = [x * 2 for x in source_iter]",
    )
    assert "doubled" in deps.defines
    assert "x" not in deps.defines  # comprehension-local
    assert "source_iter" in deps.references
