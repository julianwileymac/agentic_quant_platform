"""Generic cross-subproject import-boundary lint.

Phase 1 §4.2 of the Restructuring Plan: every subproject declares
which Python module prefixes it MUST NOT import, optionally with
narrow ``--allow`` exceptions. The lint walks one subproject's
source tree, AST-parses every ``.py`` file, and fails when any
``import`` / ``from ... import`` statement references a forbidden
prefix that is NOT covered by an allow override.

Usage::

    python scripts/ci/check_boundary.py \\
        --scan-root aqp_control_plane/src \\
        --lint-name boundary_aqp_control_plane \\
        --forbid aqp \\
        --allow aqp_platform_core \\
        --allow aqp_cp

The lint also accepts per-file allowlists at
``scripts/ci/allowlists/<lint-name>.txt`` (same format as the
Phase 0 lints).

Exit codes:
* 0 - clean
* 1 - at least one violation
* 2 - usage error / IO error
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
from _lint_allowlist import filter_violations, normalise_path  # noqa: E402


def _matches_prefix(name: str, prefix: str) -> bool:
    """``True`` if ``name`` equals ``prefix`` or is ``prefix.<sub>``."""
    if name == prefix:
        return True
    return name.startswith(prefix + ".")


def _is_forbidden(name: str, forbids: list[str], allows: list[str]) -> bool:
    """Return ``True`` when ``name`` is forbidden under the policy.

    A name is forbidden when it matches any ``--forbid`` prefix AND
    does NOT match any (longer-prefix) ``--allow`` exception. Empty
    allow lists mean every forbid match is a violation.
    """
    if not any(_matches_prefix(name, f) for f in forbids):
        return False
    if any(_matches_prefix(name, a) for a in allows):
        return False
    return True


class _BoundaryFinder(ast.NodeVisitor):
    """AST visitor collecting forbidden import statements."""

    def __init__(self, forbids: list[str], allows: list[str]) -> None:
        self.forbids = forbids
        self.allows = allows
        self.hits: list[tuple[int, str]] = []

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        # Relative imports (`from . import x`) have ``module is None``.
        module = node.module or ""
        if module and _is_forbidden(module, self.forbids, self.allows):
            names = ", ".join(alias.asname or alias.name for alias in node.names)
            self.hits.append((node.lineno, f"from {module} import {names}"))
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            if _is_forbidden(alias.name, self.forbids, self.allows):
                rendered = (
                    f"import {alias.name} as {alias.asname}"
                    if alias.asname
                    else f"import {alias.name}"
                )
                self.hits.append((node.lineno, rendered))
        self.generic_visit(node)


def _scan_file(
    path: Path, forbids: list[str], allows: list[str]
) -> list[tuple[int, str]]:
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []
    finder = _BoundaryFinder(forbids, allows)
    finder.visit(tree)
    return finder.hits


def _iter_files(scan_root: Path, excludes: list[str]) -> list[Path]:
    if not scan_root.is_dir():
        return []
    exclude_parts = {e.strip("/").replace("\\", "/") for e in excludes if e}
    out: list[Path] = []
    for p in scan_root.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        # Skip any file whose path contains an excluded directory segment.
        rel_parts = {seg for seg in p.relative_to(scan_root).parts}
        if rel_parts & exclude_parts:
            continue
        out.append(p)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scan-root",
        required=True,
        help="Subproject source directory to scan (relative to repo root).",
    )
    parser.add_argument(
        "--lint-name",
        required=True,
        help=(
            "Allowlist file stem under scripts/ci/allowlists/ "
            "(e.g. `boundary_aqp_control_plane`)."
        ),
    )
    parser.add_argument(
        "--forbid",
        action="append",
        default=[],
        required=True,
        help="Forbidden module prefix. Repeat for multiple.",
    )
    parser.add_argument(
        "--allow",
        action="append",
        default=[],
        help="Allowed module prefix exception (overrides a forbid match).",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help=(
            "Directory segment to skip beneath --scan-root (e.g. "
            "`templates`, `migrations`). Matched on any path part."
        ),
    )
    parser.add_argument(
        "--paths",
        nargs="*",
        default=None,
        help="Optional explicit file list (overrides scan-root walk).",
    )
    args = parser.parse_args(argv)

    scan_root_path = (REPO_ROOT / args.scan_root).resolve()
    if args.paths:
        files = [Path(p) for p in args.paths]
    else:
        files = _iter_files(scan_root_path, args.exclude)

    raw: list[tuple[str, str]] = []
    for path in files:
        try:
            rel = normalise_path(path.resolve().relative_to(REPO_ROOT))
        except ValueError:
            rel = normalise_path(path)
        for lineno, snippet in _scan_file(path, args.forbid, args.allow):
            raw.append((rel, f"{rel}:{lineno} {snippet}"))

    filtered = filter_violations(raw, args.lint_name)
    label = args.lint_name.replace("_", "-")
    if filtered:
        forbid_pretty = ", ".join(args.forbid)
        allow_pretty = ", ".join(args.allow) or "(none)"
        print(
            f"[{label}] FAIL: forbidden import(s) detected under "
            f"{args.scan_root}."
        )
        print(
            f"  forbid prefixes: {forbid_pretty}\n"
            f"  allow overrides: {allow_pretty}"
        )
        print(
            "\nMove the import behind the documented boundary "
            "(typically `aqp_platform_core` shared types + an HTTP "
            "client) or allowlist with a removal deadline in "
            f"scripts/ci/allowlists/{args.lint_name}.txt.\n"
        )
        for _, message in filtered:
            print(f"  - {message}")
        return 1
    print(
        f"[{label}] OK: scanned {len(files)} files, "
        f"{len(raw)} raw match(es), 0 unallowlisted."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
