"""Enforce AGENTS Rule 55 — broker credentials are BYOK only.

`Rule 55` says broker credentials (Alpaca, Interactive Brokers,
Tradier, Polygon, Binance, Coinbase, Kraken) come through the
``BrokerCredentialStore`` chain, never through direct
``settings.alpaca_*`` / ``settings.ibkr_*`` /
``settings.tradier_*`` / ``settings.polygon_*`` reads.

The sanctioned home is
``aqp/credentials/stores/broker_credential_store.py`` which is the
only module allowed to read the bootstrap settings fields. Every
other site must use ``BrokerCredentialStore.get(...)`` or
``CredentialResolver`` so multi-tenant BYOK works.

This is an AST scan: we look for ``Attribute`` nodes whose left
side is the imported ``settings`` (any alias) and whose `.attr`
matches ``<broker>_<field>`` for one of the seven brokers.

Allowlist: ``scripts/ci/allowlists/no_broker_settings.txt``.

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

EXEMPT_PREFIXES: frozenset[str] = frozenset(
    {
        "aqp/credentials/",
        # The settings object itself defines these fields.
        "aqp/config/settings.py",
        # Lint + tests reference the attribute names literally.
        "scripts/ci/",
        "tests/",
        # Docs may mention the attribute names.
        "docs/",
        "aqp_docs/",
        "AGENTS.md",
        "WORKFLOW.md",
        "RESTRUCTURING_PLAN.md",
    }
)

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

# The seven sanctioned BYOK brokers per Rule 55.
BROKER_PREFIXES: tuple[str, ...] = (
    "alpaca_",
    "ibkr_",
    "tradier_",
    "polygon_",
    "binance_",
    "coinbase_",
    "kraken_",
)


sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
from _lint_allowlist import filter_violations, normalise_path  # noqa: E402


def _is_exempt(rel_path: str) -> bool:
    return any(rel_path == p or rel_path.startswith(p) for p in EXEMPT_PREFIXES)


class _SettingsAliasFinder(ast.NodeVisitor):
    """Collect names bound to the platform settings object.

    Recognises:
    * ``from aqp.config import settings``
    * ``from aqp.config.settings import settings``
    * ``import aqp.config.settings as s``
    * ``s = settings``               (Name-to-Name alias)
    * ``cfg = get_settings()``       (heuristic on common factory)
    """

    SETTINGS_MODULES: frozenset[str] = frozenset(
        {"aqp.config", "aqp.config.settings"}
    )
    SETTINGS_FACTORIES: frozenset[str] = frozenset(
        {"get_settings", "Settings"}
    )

    def __init__(self) -> None:
        self.settings_names: set[str] = set()

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        if node.module in self.SETTINGS_MODULES:
            for alias in node.names:
                if alias.name in {"settings", "Settings", "get_settings"}:
                    self.settings_names.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            if alias.name in self.SETTINGS_MODULES:
                # rare: ``import aqp.config.settings as s``
                if alias.asname:
                    self.settings_names.add(alias.asname)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        value = node.value
        # ``cfg = settings`` or ``cfg = get_settings()``
        if isinstance(value, ast.Name) and value.id in self.settings_names:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.settings_names.add(target.id)
        elif isinstance(value, ast.Call):
            func = value.func
            if (
                isinstance(func, ast.Name)
                and func.id in self.SETTINGS_FACTORIES
            ):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.settings_names.add(target.id)
        self.generic_visit(node)


class _BrokerAttrFinder(ast.NodeVisitor):
    """Flag ``<settings-alias>.<broker>_<field>`` attribute reads."""

    def __init__(self, settings_names: set[str]) -> None:
        self.settings_names = settings_names
        self.hits: list[tuple[int, str]] = []

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        # Only the first attribute hop: settings.alpaca_api_key
        if (
            isinstance(node.value, ast.Name)
            and node.value.id in self.settings_names
            and any(node.attr.startswith(p) for p in BROKER_PREFIXES)
        ):
            self.hits.append((node.lineno, f"{node.value.id}.{node.attr}"))
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
    aliases = _SettingsAliasFinder()
    aliases.visit(tree)
    if not aliases.settings_names:
        return []
    finder = _BrokerAttrFinder(aliases.settings_names)
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

    filtered = filter_violations(raw, "no_broker_settings")
    if filtered:
        print(
            "[no-broker-settings] FAIL: direct `settings.<broker>_*` "
            "read outside `aqp/credentials/`."
        )
        print(
            "Broker credentials are BYOK only (Rule 55). Replace with "
            "`BrokerCredentialStore.get(...)` or `CredentialResolver`. "
            "Multi-tenant deployments must not share a bootstrap "
            "credential.\n"
            "Allowlist with a Phase-2 deadline in "
            "scripts/ci/allowlists/no_broker_settings.txt only if this "
            "is a documented bootstrap-only exception.\n"
        )
        for _, message in filtered:
            print(f"  - {message}")
        return 1
    print(
        f"[no-broker-settings] OK: scanned {len(files)} files, "
        f"{len(raw)} raw match(es), 0 unallowlisted."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
