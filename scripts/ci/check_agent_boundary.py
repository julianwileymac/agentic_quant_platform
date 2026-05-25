"""Enforce AGENTS Rule 22 — agent code does NOT import ``aqp.persistence``.

Walks ``aqp/agents/**/*.py`` and flags any ``from aqp.persistence`` /
``import aqp.persistence`` (or sub-module) reference. Five files are
explicit ledger-writer exceptions per the rule:

* ``aqp/agents/runtime.py``
* ``aqp/agents/registry.py``
* ``aqp/agents/evaluation.py``
* ``aqp/agents/orchestration/runtime.py``
* ``aqp/agents/orchestration/registry_specs.py``

Every other agent module must access persistence exclusively through
the DataMCP boundary (``aqp.data.mcp.tools.*`` registered tools).

Allowlist: ``scripts/ci/allowlists/agent_boundary.txt``.

Exit codes:
* 0 — clean
* 1 — at least one violation
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCAN_ROOT = REPO_ROOT / "aqp" / "agents"

# AGENTS Rule 22 — explicit ledger-writer exception files. Their job
# is to write to the run ledgers (`agent_runs_v2`, `workflow_runs`,
# `evaluation_runs`) and they own the schema invariants.
EXCEPTION_PATHS = frozenset(
    {
        "aqp/agents/runtime.py",
        "aqp/agents/registry.py",
        "aqp/agents/evaluation.py",
        "aqp/agents/orchestration/runtime.py",
        "aqp/agents/orchestration/registry_specs.py",
    }
)

BANNED_MODULE_PREFIX = "aqp.persistence"


sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
from _lint_allowlist import filter_violations, normalise_path  # noqa: E402


def _module_target(name: str) -> bool:
    """``True`` if ``name`` refers to ``aqp.persistence`` or a submodule."""
    if name == BANNED_MODULE_PREFIX:
        return True
    return name.startswith(BANNED_MODULE_PREFIX + ".")


class _BoundaryFinder(ast.NodeVisitor):
    def __init__(self) -> None:
        self.hits: list[tuple[int, str]] = []

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        module = node.module or ""
        if _module_target(module):
            names = ", ".join(alias.asname or alias.name for alias in node.names)
            self.hits.append(
                (node.lineno, f"from {module} import {names}")
            )
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            if _module_target(alias.name):
                rendered = (
                    f"import {alias.name} as {alias.asname}"
                    if alias.asname
                    else f"import {alias.name}"
                )
                self.hits.append((node.lineno, rendered))
        self.generic_visit(node)


def _scan_file(path: Path) -> list[tuple[int, str]]:
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []
    finder = _BoundaryFinder()
    finder.visit(tree)
    return finder.hits


def _iter_files() -> list[Path]:
    if not SCAN_ROOT.is_dir():
        return []
    return [
        p
        for p in SCAN_ROOT.rglob("*.py")
        if "__pycache__" not in p.parts and p.name != "__init__.py"
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--paths",
        nargs="*",
        default=None,
        help="Optional list of files to scan (defaults to aqp/agents/).",
    )
    args = parser.parse_args(argv)

    files = [Path(p) for p in args.paths] if args.paths else _iter_files()

    raw: list[tuple[str, str]] = []
    for path in files:
        rel = normalise_path(path.resolve().relative_to(REPO_ROOT))
        if rel in EXCEPTION_PATHS:
            continue
        for lineno, snippet in _scan_file(path):
            raw.append((rel, f"{rel}:{lineno} {snippet}"))

    filtered = filter_violations(raw, "agent_boundary")
    if filtered:
        print("[agent-boundary] FAIL: agent code imports `aqp.persistence`.")
        print(
            "Refactor through a registered DataMCPTool "
            "(`aqp.data.mcp.tools.*`) per AGENTS Rule 22, or allowlist "
            "with a removal deadline in "
            "scripts/ci/allowlists/agent_boundary.txt.\n"
        )
        for _, message in filtered:
            print(f"  - {message}")
        return 1
    print(
        f"[agent-boundary] OK: scanned {len(files)} files, "
        f"{len(raw)} raw match(es), 0 unallowlisted."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
