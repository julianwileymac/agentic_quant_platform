"""EDA cell DAG + kernel tests."""
from __future__ import annotations

import pytest

from aqp.lab.eda import EdaKernel, analyse_cell_dependencies, default_kernel_registry
from aqp.lab.eda.cell_dag import (
    CellNode,
    build_cell_graph,
    stale_descendants_of,
)
from aqp.lab.eda.kernel import CellSafetyError, _ast_safety_check


# ---------------------------------------------------------------------------
# AST dependency analysis
# ---------------------------------------------------------------------------


def test_dependency_analysis_extracts_defines() -> None:
    deps = analyse_cell_dependencies("c1", "x = 1\ny = x + 2")
    assert "x" in deps.defines
    assert "y" in deps.defines
    # x is defined locally so it's not a cross-cell reference.
    assert "x" not in deps.references


def test_dependency_analysis_finds_cross_cell_references() -> None:
    deps = analyse_cell_dependencies("c1", "y = upstream_value + 5")
    assert "upstream_value" in deps.references
    assert "y" in deps.defines


def test_dependency_analysis_drops_preloaded_helpers() -> None:
    # ``pd``, ``np``, ``db``, ``scan`` are preloaded — never count as
    # cross-cell references.
    deps = analyse_cell_dependencies("c1", "frame = pd.read_csv('x.csv')")
    assert "pd" not in deps.references
    assert "frame" in deps.defines


def test_dependency_analysis_handles_function_def() -> None:
    deps = analyse_cell_dependencies("c1", "def foo(a):\n    return a + 1\n")
    assert "foo" in deps.defines
    # Function body references DON'T count as cross-cell deps.
    assert "a" not in deps.references


def test_dependency_analysis_handles_class_def_references() -> None:
    deps = analyse_cell_dependencies(
        "c1",
        "class Foo:\n    members = source_data\n",
    )
    assert "Foo" in deps.defines
    # Class-level statements DO count for cross-cell deps.
    assert "source_data" in deps.references


def test_dependency_analysis_syntax_error_safe() -> None:
    deps = analyse_cell_dependencies("c1", "x = (")
    assert deps.syntax_ok is False
    assert deps.error is not None
    assert deps.defines == frozenset()


# ---------------------------------------------------------------------------
# DAG building + stale descendants
# ---------------------------------------------------------------------------


def _make_cells(spec: list[tuple[str, str]]) -> list[CellNode]:
    return [CellNode(id=cid, source=src, ord=i) for i, (cid, src) in enumerate(spec)]


def test_build_cell_graph_links_upstream_definers() -> None:
    cells = _make_cells(
        [
            ("a", "x = 10"),
            ("b", "y = x * 2"),
            ("c", "z = y + 1"),
        ]
    )
    graph = build_cell_graph(cells)
    by_id = graph.index()
    assert "a" in by_id["b"].upstream
    assert "b" in by_id["c"].upstream
    # Downstream is transitive.
    assert "c" in by_id["a"].downstream


def test_stale_descendants_orders_deterministically() -> None:
    cells = _make_cells(
        [
            ("upstream", "x = 1"),
            ("mid1", "y = x + 1"),
            ("mid2", "z = x * 2"),
            ("leaf", "w = y + z"),
        ]
    )
    graph = build_cell_graph(cells)
    stale = stale_descendants_of(graph, "upstream")
    assert stale == sorted(stale)
    assert {"mid1", "mid2", "leaf"}.issubset(set(stale))


# ---------------------------------------------------------------------------
# AST safety guard
# ---------------------------------------------------------------------------


def test_safety_guard_rejects_os_system() -> None:
    with pytest.raises(CellSafetyError):
        _ast_safety_check("import os\nos.system('echo pwned')")


def test_safety_guard_rejects_subprocess_import() -> None:
    with pytest.raises(CellSafetyError):
        _ast_safety_check("import subprocess")


def test_safety_guard_rejects_eval() -> None:
    with pytest.raises(CellSafetyError):
        _ast_safety_check("eval('1 + 1')")


def test_safety_guard_allows_safe_pandas() -> None:
    # No exception expected.
    _ast_safety_check("import pandas as pd\ndf = pd.DataFrame({'x':[1,2]})")


# ---------------------------------------------------------------------------
# Kernel execution
# ---------------------------------------------------------------------------


def test_kernel_executes_cell_and_persists_namespace() -> None:
    kernel = EdaKernel("test-session")
    r1 = kernel.execute_cell("a", "x = 7")
    assert r1.status == "done"
    r2 = kernel.execute_cell("b", "y = x * 6")
    assert r2.status == "done"
    assert kernel.get_var("y") == 42


def test_kernel_captures_stdout_and_repr() -> None:
    kernel = EdaKernel("test-session")
    r = kernel.execute_cell("a", "print('hi')\n42 + 1")
    assert r.status == "done"
    assert "hi" in r.stdout
    assert r.repr_value == "43"


def test_kernel_reports_runtime_error() -> None:
    kernel = EdaKernel("test-session")
    r = kernel.execute_cell("a", "1 / 0")
    assert r.status == "error"
    assert "ZeroDivisionError" in (r.error or "") or "division" in (r.error or "").lower()


def test_kernel_rejects_unsafe_cell() -> None:
    kernel = EdaKernel("test-session")
    r = kernel.execute_cell("a", "import subprocess\nsubprocess.run(['ls'])")
    assert r.status == "error"
    assert "forbidden" in (r.error or "").lower()


def test_kernel_marks_descendants_stale_on_edit() -> None:
    kernel = EdaKernel("test-session")
    kernel.execute_cell("a", "x = 1")
    kernel.execute_cell("b", "y = x + 1")
    # Re-add cell a — descendants should be marked stale.
    kernel.upsert_cell("a", "x = 99")
    snapshot = kernel.graph_snapshot()
    by_id = snapshot.index()
    assert by_id["b"].stale is True


def test_kernel_registry_is_session_scoped() -> None:
    registry = default_kernel_registry()
    k1 = registry.get_or_create("sess-1")
    k2 = registry.get_or_create("sess-2")
    assert k1 is not k2
    k1.execute_cell("a", "shared = 'one'")
    k2.execute_cell("a", "shared = 'two'")
    assert k1.get_var("shared") == "one"
    assert k2.get_var("shared") == "two"
    registry.remove("sess-1")
    registry.remove("sess-2")
