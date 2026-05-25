"""Enforce AGENTS Rule 11 — RAG queries route through ``aqp/rag/``.

The hierarchical RAG layer at :mod:`aqp.rag.hierarchy` is the only
sanctioned caller of Redis Search (``FT.SEARCH``,
``FT.CREATE`` etc.). It owns the index naming convention, the
per-cell pgvector fallback handshake and the metric exporter
contract. Direct ``redis_client.ft(...)`` (or
``await redis_client.ft(...)``) anywhere else bypasses the
sharding, retry budget and cell-router resolution and so is
banned by Rule 11.

Allowlist: ``scripts/ci/allowlists/no_direct_redis_ft.txt``.

Exit codes:
* 0 - clean
* 1 - at least one violation
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Sanctioned callers. POSIX-style relative to the repo root.
EXEMPT_PREFIXES: frozenset[str] = frozenset(
    {
        "aqp/rag/",
        # Lint + tests reference the call shape literally.
        "scripts/ci/",
        "tests/ci/",
    }
)

# Skip noisy / generated subtrees.
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

_REDIS_IMPORT_HINTS: frozenset[str] = frozenset(
    {"redis", "redis.asyncio", "redis.client", "redis.commands.search", "aioredis"}
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


class _RedisAliasFinder(ast.NodeVisitor):
    """Find names bound to a `redis*` import or `redis.Redis(...)` result."""

    def __init__(self) -> None:
        self.bound_to_redis: set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            if alias.name in _REDIS_IMPORT_HINTS:
                self.bound_to_redis.add(alias.asname or alias.name.split(".")[0])
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        if node.module in _REDIS_IMPORT_HINTS:
            for alias in node.names:
                self.bound_to_redis.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        value = node.value
        if isinstance(value, ast.Call):
            chain = _attr_chain(value.func)
            if chain and chain[0] in self.bound_to_redis:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.bound_to_redis.add(target.id)
        self.generic_visit(node)


class _FtCallFinder(ast.NodeVisitor):
    """Flag ``<redis-bound>.ft(...)`` calls."""

    def __init__(self, redis_names: set[str]) -> None:
        self.redis_names = redis_names
        self.hits: list[tuple[int, str]] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "ft":
            chain = _attr_chain(func)
            if chain and chain[0] in self.redis_names:
                self.hits.append((node.lineno, ".".join(chain) + "(...)"))
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
    aliases = _RedisAliasFinder()
    aliases.visit(tree)
    if not aliases.bound_to_redis:
        return []
    finder = _FtCallFinder(aliases.bound_to_redis)
    finder.visit(tree)
    return finder.hits


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

    filtered = filter_violations(raw, "no_direct_redis_ft")
    if filtered:
        print("[no-direct-redis-ft] FAIL: redis_client.ft(...) outside aqp/rag/.")
        print(
            "Route RAG queries through the canonical "
            "`aqp.rag.hierarchy` entry points (Rule 11). The RAG layer "
            "owns the per-cell index naming, sharding and pgvector "
            "fallback.\n"
            "Allowlist with a Phase-2 deadline in "
            "scripts/ci/allowlists/no_direct_redis_ft.txt if the call "
            "genuinely belongs in `aqp/rag/` but lives outside its "
            "tree today.\n"
        )
        for _, message in filtered:
            print(f"  - {message}")
        return 1
    print(
        f"[no-direct-redis-ft] OK: scanned {len(files)} files, "
        f"{len(raw)} raw match(es), 0 unallowlisted."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
