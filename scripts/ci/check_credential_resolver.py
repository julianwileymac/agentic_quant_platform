"""Enforce AGENTS Rule 26 — credentials flow through ``CredentialResolver``.

AST-based scan that flags attribute reads on names that resolve to the
``aqp.config.settings`` singleton (or its ``Settings`` class) and
target a credential-shaped field name.

A credential-shaped field is any name matching one of the suffixes
defined in :data:`CREDENTIAL_SUFFIXES`:

* ``_token``, ``_secret``, ``_credential``, ``_credentials``
* ``_api_key``, ``_apikey``, ``_password``, ``_passphrase``
* ``_private_key``, ``_signing_key``

Exempt directories (the lint never flags reads here):

* ``aqp/config/`` — Pydantic Settings home
* ``aqp/credentials/`` — the canonical resolver / store implementations
* ``aqp_platform/rollback/`` — frozen rollback artefacts (Rule 47 path)

Allowlist: ``scripts/ci/allowlists/credential_resolver.txt``.

Exit codes:
* 0 — no violations (after allowlist)
* 1 — at least one violation
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Lint scope — we walk these top-level dirs, then exclude the exempt
# subtrees inside them.
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

EXEMPT_PREFIXES = (
    "aqp/config/",
    "aqp/credentials/",
    "aqp_platform/rollback/",
)

CREDENTIAL_SUFFIXES = (
    "_token",
    "_secret",
    "_credential",
    "_credentials",
    "_api_key",
    "_apikey",
    "_password",
    "_passphrase",
    "_private_key",
    "_signing_key",
)

# Names commonly bound to the global settings singleton.
SETTINGS_BINDING_NAMES = ("settings", "Settings", "_settings", "config_settings")


sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
from _lint_allowlist import filter_violations, normalise_path  # noqa: E402


def _is_credential_attr(name: str) -> bool:
    lower = name.lower()
    return any(lower.endswith(suffix) for suffix in CREDENTIAL_SUFFIXES)


class _SettingsAliasFinder(ast.NodeVisitor):
    """Collect names that are aliases for the ``aqp.config.settings`` singleton.

    Picks up:

    * ``from aqp.config import settings`` -> ``settings``
    * ``from aqp.config import settings as foo`` -> ``foo``
    * ``import aqp.config as cfg`` -> ``cfg.settings``
    * ``from aqp.config.settings import Settings`` -> ``Settings`` (class
      itself; reads on it are still credential-shaped if they hit a
      Field).
    """

    def __init__(self) -> None:
        self.bound_names: set[str] = set()
        self.module_aliases: set[str] = set()  # `cfg` for `import aqp.config as cfg`

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        if (node.module or "").startswith("aqp.config"):
            for alias in node.names:
                if alias.name in ("settings", "Settings"):
                    self.bound_names.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            if alias.name == "aqp.config" or alias.name.startswith("aqp.config."):
                self.module_aliases.add(alias.asname or alias.name.replace(".", "_"))
        self.generic_visit(node)


class _CredentialReadFinder(ast.NodeVisitor):
    def __init__(self, *, settings_names: set[str], module_aliases: set[str]) -> None:
        self.settings_names = settings_names
        self.module_aliases = module_aliases
        self.violations: list[tuple[int, str]] = []

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        if not _is_credential_attr(node.attr):
            self.generic_visit(node)
            return
        # Direct binding: settings.foo_token
        if isinstance(node.value, ast.Name) and node.value.id in self.settings_names:
            self.violations.append((node.lineno, f"{node.value.id}.{node.attr}"))
        # Module alias: cfg.settings.foo_token
        elif (
            isinstance(node.value, ast.Attribute)
            and node.value.attr == "settings"
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id in self.module_aliases
        ):
            self.violations.append((node.lineno, f"{node.value.value.id}.settings.{node.attr}"))
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
    aliases = _SettingsAliasFinder()
    aliases.visit(tree)
    if not aliases.bound_names and not aliases.module_aliases:
        return []
    finder = _CredentialReadFinder(
        settings_names=aliases.bound_names,
        module_aliases=aliases.module_aliases,
    )
    finder.visit(tree)
    return finder.violations


def _is_exempt(rel_path: str) -> bool:
    return any(rel_path.startswith(prefix) for prefix in EXEMPT_PREFIXES)


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for root_name in SCAN_ROOTS:
        root = REPO_ROOT / root_name
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            rel = normalise_path(path.resolve().relative_to(REPO_ROOT))
            if _is_exempt(rel):
                continue
            # Skip build / cache / virtualenv junk.
            if "__pycache__" in path.parts or ".venv" in path.parts:
                continue
            files.append(path)
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--paths",
        nargs="*",
        default=None,
        help="Optional list of paths to scan (defaults to the SCAN_ROOTS).",
    )
    args = parser.parse_args(argv)

    files = [Path(p) for p in args.paths] if args.paths else _iter_python_files()

    raw: list[tuple[str, str]] = []
    for path in files:
        for lineno, expr in _scan_file(path):
            rel = normalise_path(path.resolve().relative_to(REPO_ROOT))
            if _is_exempt(rel):
                continue
            raw.append((rel, f"{rel}:{lineno} reads {expr}"))

    filtered = filter_violations(raw, "credential_resolver")
    if filtered:
        print("[credential-resolver] FAIL: direct settings.<x>_<credential> reads detected.")
        print(
            "Each violation must route through `get_resolver().resolve("
            "CredentialKey(...))` or be added to "
            "`scripts/ci/allowlists/credential_resolver.txt` with a "
            "removal deadline.\n"
        )
        for _, message in filtered:
            print(f"  - {message}")
        return 1
    print(
        f"[credential-resolver] OK: scanned {len(files)} files, "
        f"{len(raw)} raw match(es), 0 unallowlisted."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
