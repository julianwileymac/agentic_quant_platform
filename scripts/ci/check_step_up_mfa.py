"""Enforce AGENTS Rule 52 — destructive routes carry step-up MFA.

Per RFC 9470 + AGENTS hard rule 52, every destructive route in the
canonical destructive-route list MUST attach
``Depends(require_step_up(...))`` somewhere in its FastAPI decorator
stack (either as a route ``dependencies=[...]`` or as a function
parameter default).

The canonical list lives in this lint script (see
:data:`DESTRUCTIVE_ROUTES`). When a new destructive route is added,
update this list and the matching test fixture.

Lint heuristic:
* Walk every ``@router.<method>("/path", ...)`` decorator in
  ``aqp*/api/routes/`` and the four embedded route modules in
  ``aqp_rl`` / ``aqp_models`` / ``aqp_control_plane`` /
  ``aqp_ratelimit``.
* For each decorator whose ``(method, path)`` matches a destructive
  pattern, verify ``require_step_up`` appears either as
  ``dependencies=[Depends(require_step_up(...))]`` (or ``_require_step_up``
  shim — see ``aqp_ratelimit/api/routes/ratelimit.py``) or as a
  function-parameter ``Depends(require_step_up(...))``.

False-positives can be suppressed via the allowlist; false-negatives
are minimised by widening the regex to match common path templates.

Allowlist: ``scripts/ci/allowlists/step_up_mfa.txt``.

Exit codes:
* 0 - clean
* 1 - at least one destructive route without step-up MFA
"""

from __future__ import annotations

import argparse
import ast
import re
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

# Lint script + tests reference the strings literally, and the dep
# helper itself defines `require_step_up`.
EXEMPT_PREFIXES: frozenset[str] = frozenset(
    {
        "scripts/ci/",
        "tests/",
        "aqp/api/security_stepup.py",
    }
)


# Canonical destructive-route list. Each entry is a `(methods, path_regex,
# label)` tuple. Methods are upper-case HTTP verbs. Paths are matched as
# Python regex against the route decorator's path argument concatenated
# with its parent router prefix when known. When the router prefix
# cannot be resolved at parse time we fall back to matching on the raw
# decorator path alone — the regexes below allow either shape.
DESTRUCTIVE_ROUTES: tuple[tuple[frozenset[str], re.Pattern[str], str], ...] = (
    # Kill switch — Rule 52 canonical example.
    (
        frozenset({"POST"}),
        re.compile(r"(?:^|/)portfolio/kill_switch$"),
        "portfolio kill switch",
    ),
    # `/halt` and `/halt-all` endpoints across subsystems.
    (
        frozenset({"POST"}),
        re.compile(r"(?:^|/)halt(?:-all|/all)?$"),
        "subsystem halt",
    ),
    # BYOK broker credential mutations.
    (
        frozenset({"POST", "DELETE", "PATCH", "PUT"}),
        re.compile(r"(?:^|/)broker[_-]credentials(?:/.*)?$"),
        "broker credential mutation",
    ),
    # User OAuth credential deletes.
    (
        frozenset({"DELETE"}),
        re.compile(r"(?:^|/)oauth[-_]connections?/.*$"),
        "user OAuth connection delete",
    ),
    # Terraform apply / destroy via the control plane.
    (
        frozenset({"POST", "DELETE"}),
        re.compile(r"(?:^|/)terraform/(apply|destroy|workloads/.*)$"),
        "terraform apply/destroy",
    ),
    # Organization invite issuance.
    (
        frozenset({"POST"}),
        re.compile(r"(?:^|/)organizations?/.+/invites?$"),
        "organization invite issuance",
    ),
    # Tenancy strategy migration (admin).
    (
        frozenset({"POST"}),
        re.compile(r"(?:^|/)tenancy/(strategy|migrate)$"),
        "tenancy strategy migration",
    ),
    # Rate-limit reservations + key lifecycle.
    (
        frozenset({"POST"}),
        re.compile(r"(?:^|/)reserve$"),
        "rate-limit reserve",
    ),
    (
        frozenset({"DELETE"}),
        re.compile(r"(?:^|/)reservations?/.+$"),
        "rate-limit reservation delete",
    ),
    (
        frozenset({"POST", "DELETE"}),
        re.compile(r"(?:^|/)me/keys(?:/.+)?$"),
        "per-user vendor key lifecycle",
    ),
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


def _expr_contains_require_step_up(node: ast.AST) -> bool:
    """Return True if the AST subtree contains a ``require_step_up``
    reference (call, attribute, or name)."""
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id in {
            "require_step_up",
            "_require_step_up",
        }:
            return True
        if isinstance(child, ast.Attribute) and child.attr in {
            "require_step_up",
            "_require_step_up",
        }:
            return True
    return False


def _function_has_step_up_dep(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Inspect a route handler function for a ``Depends(require_step_up(...))``
    parameter default."""
    args = func.args
    defaults = list(args.defaults) + list(args.kw_defaults or [])
    for default in defaults:
        if default is None:
            continue
        if _expr_contains_require_step_up(default):
            return True
    return False


def _decorator_has_step_up_dep(decorator: ast.Call) -> bool:
    """Inspect ``@router.post('/x', dependencies=[...])`` for step-up."""
    for kw in decorator.keywords:
        if kw.arg == "dependencies" and _expr_contains_require_step_up(kw.value):
            return True
    return False


def _resolve_router_prefix(tree: ast.Module) -> str:
    """Best-effort pluck of ``APIRouter(prefix="…")`` constants in module."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            chain = _attr_chain(node.value.func)
            if chain and chain[-1] == "APIRouter":
                for kw in node.value.keywords:
                    if (
                        kw.arg == "prefix"
                        and isinstance(kw.value, ast.Constant)
                        and isinstance(kw.value.value, str)
                    ):
                        return kw.value.value
    return ""


class _RouteFinder(ast.NodeVisitor):
    """Collect destructive-route violations across a single module."""

    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.hits: list[tuple[int, str]] = []

    def _check_decorator(
        self,
        decorator: ast.Call,
        func: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        chain = _attr_chain(decorator.func)
        if not chain or len(chain) < 2:
            return
        method = chain[-1].upper()
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            return
        if not decorator.args:
            return
        path_arg = decorator.args[0]
        if not isinstance(path_arg, ast.Constant) or not isinstance(path_arg.value, str):
            return
        path = path_arg.value
        full_path = (self.prefix.rstrip("/") + "/" + path.lstrip("/")).rstrip("/")
        if not full_path.startswith("/"):
            full_path = "/" + full_path
        for methods, regex, label in DESTRUCTIVE_ROUTES:
            if method not in methods:
                continue
            if not (regex.search(path) or regex.search(full_path)):
                continue
            if _decorator_has_step_up_dep(decorator):
                return
            if _function_has_step_up_dep(func):
                return
            self.hits.append(
                (
                    decorator.lineno,
                    f"{method} {full_path} ({label}) missing require_step_up",
                )
            )
            return

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call):
                self._check_decorator(dec, node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call):
                self._check_decorator(dec, node)
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
    prefix = _resolve_router_prefix(tree)
    finder = _RouteFinder(prefix)
    finder.visit(tree)
    return finder.hits


def _iter_files() -> list[Path]:
    return [p for p in REPO_ROOT.rglob("*.py") if not (SKIP_PARTS & set(p.parts))]


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

    filtered = filter_violations(raw, "step_up_mfa")
    if filtered:
        print("[step-up-mfa] FAIL: destructive route without `Depends(require_step_up(...))`.")
        print(
            "Every route in the canonical destructive-route list MUST "
            "attach `require_step_up` (Rule 52). RFC 9470 step-up MFA "
            "neutralises stolen-session replay against the kill switch, "
            "halts, BYOK credential mutations, OAuth credential deletes, "
            "Terraform apply/destroy, organization invite issuance, "
            "tenancy strategy migration, and rate-limit reservation / "
            "key lifecycle.\n"
            "Allowlist with a Phase-2 deadline in "
            "scripts/ci/allowlists/step_up_mfa.txt only if the route is "
            "an internal-only fixture or scaffold.\n"
        )
        for _, message in filtered:
            print(f"  - {message}")
        return 1
    print(
        f"[step-up-mfa] OK: scanned {len(files)} files, {len(raw)} raw match(es), 0 unallowlisted."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
