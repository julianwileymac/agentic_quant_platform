"""Ban Pydantic V1 serialisation methods.

Pydantic V2 replaced ``model.dict()`` / ``Model.parse_obj(...)`` /
``Model.parse_raw(...)`` / ``Model.from_orm(...)`` with
``model_dump`` / ``model_validate`` / ``model_validate_json`` /
``model_validate(... from_attributes=True)``. Mixing the two surfaces
in the same codebase is a runtime trap.

Heuristic: AST scan that flags

* ``<expr>.dict(...)`` calls in files that import from ``pydantic``
* ``<expr>.parse_obj(...)`` calls
* ``<expr>.parse_raw(...)`` calls
* ``<expr>.from_orm(...)`` calls

The heuristic only fires when the module imports ``pydantic`` (or
``BaseModel`` from it), which keeps unrelated calls like
``some_dict.dict`` from tripping the lint.

Allowlist: ``scripts/ci/allowlists/no_pydantic_v1.txt``.

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

SCAN_ROOTS = (
    "aqp",
    "aqp_bots",
    "aqp_rl",
    "aqp_models",
    "aqp_platform",
    "aqp_control_plane",
    "aqp_platform_core",
    "aqp_cli",
    "aqp_admin",
    "aqp_ide",
)

V1_METHOD_NAMES = frozenset(
    {
        "dict",
        "parse_obj",
        "parse_raw",
        "from_orm",
    }
)


sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
from _lint_allowlist import filter_violations, normalise_path  # noqa: E402


def _imports_pydantic(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "pydantic" or alias.name.startswith("pydantic."):
                    return True
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "pydantic" or mod.startswith("pydantic."):
                return True
    return False


class _PydanticV1Finder(ast.NodeVisitor):
    def __init__(self) -> None:
        self.hits: list[tuple[int, str]] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in V1_METHOD_NAMES:
            # Skip cases where the receiver is obviously a ``dict``
            # built-in or a literal mapping. Best effort — anything we
            # can't statically prove is reported.
            base = ast.unparse(func.value) if hasattr(ast, "unparse") else "?"
            # ``foo.dict()`` on a literal dict access pattern is rare;
            # rely on the import gate to filter.
            self.hits.append(
                (
                    node.lineno,
                    f"{base}.{func.attr}({_args_label(node)})",
                )
            )
        self.generic_visit(node)


def _args_label(node: ast.Call) -> str:
    n = len(node.args) + len(node.keywords)
    if n == 0:
        return ""
    return f"<{n} arg{'s' if n != 1 else ''}>"


def _scan_file(path: Path) -> list[tuple[int, str]]:
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []
    if not _imports_pydantic(tree):
        return []
    finder = _PydanticV1Finder()
    finder.visit(tree)
    return finder.hits


def _iter_files() -> list[Path]:
    files: list[Path] = []
    for root_name in SCAN_ROOTS:
        root = REPO_ROOT / root_name
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts or ".venv" in path.parts:
                continue
            files.append(path)
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paths", nargs="*", default=None)
    args = parser.parse_args(argv)

    files = [Path(p) for p in args.paths] if args.paths else _iter_files()

    raw: list[tuple[str, str]] = []
    for path in files:
        for lineno, expr in _scan_file(path):
            rel = normalise_path(path.resolve().relative_to(REPO_ROOT))
            raw.append((rel, f"{rel}:{lineno} {expr}"))

    filtered = filter_violations(raw, "no_pydantic_v1")
    if filtered:
        print("[no-pydantic-v1] FAIL: Pydantic V1 serialisation method(s) detected.")
        print(
            "Replace `.dict(...)` -> `.model_dump(...)`, "
            "`.parse_obj(...)` -> `.model_validate(...)`, "
            "`.parse_raw(...)` -> `.model_validate_json(...)`, "
            "`.from_orm(...)` -> `.model_validate(..., from_attributes=True)`.\n"
        )
        for _, message in filtered:
            print(f"  - {message}")
        return 1
    print(
        f"[no-pydantic-v1] OK: scanned {len(files)} files, "
        f"{len(raw)} raw match(es), 0 unallowlisted."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
