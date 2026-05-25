"""Enforce AGENTS Rule 49 — every MCP server validates RFC 8707 audience.

The 2025-11-25 MCP authorization spec MUST clause requires every MCP
server to validate that incoming access tokens are issued for the
server's canonical URI (RFC 8707 / RFC 9728). AQP's runtime helper
lives at :func:`aqp.api.mcp_audience.validate_mcp_audience`. Any new
MCP router that exposes a tool-invocation surface MUST call it before
dispatching the tool.

Lint heuristic:
* Find every Python module that constructs an
  ``APIRouter(prefix="/mcp/...")``.
* Verify it imports ``validate_mcp_audience`` AND calls it somewhere.

False-negatives are kept low because the only blessed audience helper
is ``aqp.api.mcp_audience``; modules that route through a different
helper would fail the import check and be flagged.

Allowlist: ``scripts/ci/allowlists/mcp_audience.txt``.

Exit codes:
* 0 - clean
* 1 - at least one MCP router without audience validation
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

SKIP_PARTS: frozenset[str] = frozenset(
    {
        "__pycache__",
        ".venv",
        "venv",
        "node_modules",
        ".git",
        "site-packages",
        "vendor",
    }
)

# Lint script + tests reference the strings literally.
EXEMPT_PREFIXES: frozenset[str] = frozenset(
    {
        "scripts/ci/",
        "tests/",
        # The audience helper itself.
        "aqp/api/mcp_audience.py",
    }
)


sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
from _lint_allowlist import filter_violations, normalise_path  # noqa: E402


def _is_exempt(rel_path: str) -> bool:
    return any(rel_path == p or rel_path.startswith(p) for p in EXEMPT_PREFIXES)


def _attr_chain(node: ast.AST) -> list[str] | None:
    parts: list[str] = []
    cur: ast.AST = node
    while True:
        if isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        elif isinstance(cur, ast.Name):
            parts.append(cur.id)
            return list(reversed(parts))
        else:
            return None


def _string_kw(call: ast.Call, name: str) -> str | None:
    """Return the literal string value of a keyword argument if present."""
    for kw in call.keywords:
        if kw.arg == name and isinstance(kw.value, ast.Constant):
            value = kw.value.value
            if isinstance(value, str):
                return value
    return None


class _McpRouterFinder(ast.NodeVisitor):
    """Collect ``APIRouter(prefix="/mcp/...")`` constructions and any
    calls to ``validate_mcp_audience(...)`` in the same module."""

    def __init__(self) -> None:
        self.has_mcp_router: bool = False
        self.mcp_router_lineno: int | None = None
        self.calls_validator: bool = False
        self.imports_validator: bool = False

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        if (node.module or "").endswith("mcp_audience"):
            for alias in node.names:
                if alias.name == "validate_mcp_audience":
                    self.imports_validator = True
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        chain = _attr_chain(node.func)
        if chain:
            tail = chain[-1]
            # APIRouter(prefix="/mcp/...")
            if tail == "APIRouter":
                prefix = _string_kw(node, "prefix")
                if prefix and prefix.startswith("/mcp/"):
                    self.has_mcp_router = True
                    self.mcp_router_lineno = node.lineno
            # validate_mcp_audience(...)
            elif tail == "validate_mcp_audience":
                self.calls_validator = True
        self.generic_visit(node)


def _scan_file(path: Path) -> list[tuple[int, str]]:
    try:
        source = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []
    visitor = _McpRouterFinder()
    visitor.visit(tree)
    if not visitor.has_mcp_router:
        return []
    if visitor.imports_validator and visitor.calls_validator:
        return []
    lineno = visitor.mcp_router_lineno or 1
    missing: list[str] = []
    if not visitor.imports_validator:
        missing.append("imports validate_mcp_audience")
    if not visitor.calls_validator:
        missing.append("calls validate_mcp_audience(...)")
    return [(lineno, f"MCP router missing: {' / '.join(missing)}")]


def _iter_files() -> list[Path]:
    return [
        p for p in REPO_ROOT.rglob("*.py") if not (SKIP_PARTS & set(p.parts))
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paths", nargs="*", default=None)
    args = parser.parse_args(argv)

    files = [Path(p) for p in args.paths] if args.paths else _iter_files()

    raw: list[tuple[str, str]] = []
    for path in files:
        try:
            rel = normalise_path(path.resolve().relative_to(REPO_ROOT))
        except ValueError:
            rel = normalise_path(path)
        if _is_exempt(rel):
            continue
        for lineno, snippet in _scan_file(path):
            raw.append((rel, f"{rel}:{lineno} {snippet}"))

    filtered = filter_violations(raw, "mcp_audience")
    if filtered:
        print(
            "[mcp-audience] FAIL: MCP router without RFC 8707 audience "
            "validation."
        )
        print(
            "Every `APIRouter(prefix=\"/mcp/...\")` MUST call "
            "`validate_mcp_audience(request, <canonical_uri>, "
            "mode=...)` (Rule 49). Without this check, a token minted "
            "for one MCP server can be replayed against another.\n"
            "Allowlist with a Phase-2 deadline in "
            "scripts/ci/allowlists/mcp_audience.txt only if there is "
            "a documented reason (e.g. an internal-only stdio bridge "
            "with no token surface).\n"
        )
        for _, message in filtered:
            print(f"  - {message}")
        return 1
    print(
        f"[mcp-audience] OK: scanned {len(files)} files, "
        f"{len(raw)} raw match(es), 0 unallowlisted."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
