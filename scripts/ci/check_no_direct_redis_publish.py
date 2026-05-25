"""Enforce AGENTS Rule 4 — Redis publish goes through ``_progress.emit``.

Walks the repo for direct ``redis.publish(...)`` /
``redis_client.publish(...)`` / ``await r.publish(...)`` style calls
and fails when the caller is outside the three sanctioned modules:

* ``aqp/tasks/_progress.py`` — the canonical publisher.
* ``aqp/ws/`` — WebSocket fan-out layer.
* ``aqp/cache/`` — cache-invalidation broadcasts.

Direct `redis.publish` calls anywhere else bypass the task progress
plumbing and break consumers that depend on the structured
``ProgressEvent`` envelope.

Allowlist: ``scripts/ci/allowlists/no_direct_redis_publish.txt``.

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

# Canonical publishers. Paths are POSIX-style relative to repo root
# to match the allowlist normaliser.
EXEMPT_PREFIXES: frozenset[str] = frozenset(
    {
        "aqp/tasks/_progress.py",
        "aqp/ws/",
        "aqp/cache/",
        # The lint script itself + its tests touch the string literally.
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
        # Vendored Renovate / Dependabot fixtures in subprojects
        # generate Python; ignore.
        "site-packages",
        # IDE bundles (Theia, npm) ship Python under node_modules but
        # also under their own vendor paths.
        "vendor",
    }
)

# Modules typically aliased to a redis client. We don't enforce a
# fixed receiver name — the AST visit recognises any
# ``<expr>.publish(...)`` whose callee attribute is `publish` and
# whose argument-zero arg pattern matches a "channel string". We
# refine this with a focused redis-import discovery pass first to
# avoid false-positives on Kafka producer ``.publish()`` calls.
_REDIS_IMPORT_HINTS: frozenset[str] = frozenset(
    {"redis", "redis.asyncio", "redis.client", "aioredis"}
)


sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
from _lint_allowlist import filter_violations, normalise_path  # noqa: E402


def _is_exempt(rel_path: str) -> bool:
    for prefix in EXEMPT_PREFIXES:
        if rel_path == prefix or rel_path.startswith(prefix):
            return True
    return False


class _RedisAliasFinder(ast.NodeVisitor):
    """First pass — collect names bound to a `redis*` import.

    We track:
    * ``import redis`` / ``import redis.asyncio as r`` -> name
    * ``from redis import Redis`` -> attribute path on instance later
    * ``redis_client = redis.Redis(...)`` / ``= redis.from_url(...)``
      bound to a local name.
    """

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
        # ``x = redis.from_url(...)`` / ``x = redis.Redis(...)``
        value = node.value
        if isinstance(value, ast.Call):
            func = value.func
            chain = _attr_chain(func)
            if chain and chain[0] in self.bound_to_redis:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.bound_to_redis.add(target.id)
        self.generic_visit(node)


def _attr_chain(node: ast.AST) -> list[str] | None:
    """Return the dotted attribute chain rooted at a Name, else None.

    e.g. ``redis.client.publish`` -> ``["redis", "client", "publish"]``.
    """
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


class _PublishCallFinder(ast.NodeVisitor):
    """Second pass — flag ``<redis-bound>.publish(...)`` calls."""

    def __init__(self, redis_names: set[str]) -> None:
        self.redis_names = redis_names
        self.hits: list[tuple[int, str]] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        func = node.func
        # Cover plain ``x.publish(...)`` and ``await x.publish(...)``.
        if isinstance(func, ast.Attribute) and func.attr == "publish":
            chain = _attr_chain(func)
            if chain and chain[0] in self.redis_names:
                snippet = ".".join(chain) + "(...)"
                self.hits.append((node.lineno, snippet))
        self.generic_visit(node)

    # `await ...publish(...)` is just a Call node wrapped in Await;
    # the default generic_visit walks into it.


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
    finder = _PublishCallFinder(aliases.bound_to_redis)
    finder.visit(tree)
    return finder.hits


def _iter_files() -> list[Path]:
    out: list[Path] = []
    for p in REPO_ROOT.rglob("*.py"):
        if SKIP_PARTS & set(p.parts):
            continue
        out.append(p)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--paths",
        nargs="*",
        default=None,
        help="Optional list of files to scan (defaults to full repo walk).",
    )
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

    filtered = filter_violations(raw, "no_direct_redis_publish")
    if filtered:
        print("[no-direct-redis-publish] FAIL: direct redis.publish() outside sanctioned modules.")
        print(
            "Route progress events through `aqp.tasks._progress.emit(...)` "
            "(Rule 4). WebSocket fan-out belongs in `aqp/ws/`; cache "
            "invalidation broadcasts in `aqp/cache/`.\n"
            "Allowlist with a Phase-2 deadline in "
            "scripts/ci/allowlists/no_direct_redis_publish.txt if the "
            "call genuinely belongs to one of those layers but lives "
            "outside its tree today.\n"
        )
        for _, message in filtered:
            print(f"  - {message}")
        return 1
    print(
        f"[no-direct-redis-publish] OK: scanned {len(files)} files, "
        f"{len(raw)} raw match(es), 0 unallowlisted."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
