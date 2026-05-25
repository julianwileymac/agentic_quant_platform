"""Enforce AGENTS Rule 47 — topology service owns service URLs.

The topology service at :mod:`aqp.config.topology_fallback` returns
per-cell, per-tenant service URLs from
`aqp_platform/configs/deployment/topology.yaml`. Hardcoded
``*-service.svc.cluster.local`` URLs inside Python / YAML / shell
make the codebase un-relocatable when a tenant is sharded onto a
new cell, so Rule 47 bans them outside the topology service's own
home.

This is a substring scan rather than an AST scan because the
violation pattern is a string literal that may appear inside
log messages, dataclasses or templated f-strings.

Sanctioned homes:
* ``aqp/config/``                            — topology service code
* ``aqp_platform/configs/deployment/``       — topology YAML
* ``aqp_platform/deployments/``              — k8s manifests
* ``aqp_platform/terraform/``                — IaC modules
* ``docs/`` / ``aqp_docs/``                  — documentation
* ``scripts/ci/`` + ``tests/``               — fixtures/tests

Allowlist: ``scripts/ci/allowlists/no_hardcoded_svc_urls.txt``.

Exit codes:
* 0 - clean
* 1 - at least one violation
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

EXEMPT_PREFIXES: frozenset[str] = frozenset(
    {
        # Topology service homes — the canonical owners of service URLs.
        "aqp/config/",
        "aqp_platform_core/src/aqp_platform_core/connectivity/",
        # Deployment surface — k8s manifests, helm charts, terraform IaC,
        # compose files, scaffolding templates, bootstrap scripts and
        # legacy rollback paths legitimately bake in cluster DNS names.
        "aqp_platform/configs/",
        "aqp_platform/deployments/",
        "aqp_platform/terraform/",
        "aqp_platform/compose/",
        "aqp_platform/templates/",
        "aqp_platform/scripts/cluster_install/",
        "aqp_platform/rollback/",
        # Pipeline runtime config — env-backed defaults that mirror the
        # topology service for Argo / Dagster bootstrap.
        "aqp_platform/pipelines/config.py",
        # Per-subproject k8s deployment manifests.
        "aqp_ratelimit/envoy/",
        "aqp_platform/deploy/k8s/",
        # Argo / Dagster user-code defs ship the cluster service DNS
        # name as the default API endpoint — that IS the deployment
        # config for the pipeline.
        "aqp_platform/pipelines/dagster_user_code/",
        # Kernel pod templates inject the cluster service DNS for the
        # rl-proxy sidecar; pod manifests are deployment surface.
        "aqp_kernels/pods/templates/",
        # Docs, lint sources and tests reference the URL pattern literally.
        "docs/",
        "aqp_docs/",
        "scripts/ci/",
        "tests/",
        # Nested `tests/` directories under each subproject — these
        # legitimately assert against the cluster DNS pattern.
        "aqp_platform_core/tests/",
        "aqp_platform/tests/",
        "aqp_control_plane/tests/",
        "aqp_admin/tests/",
        "aqp_client/tests/",
        "aqp_ui/tests/",
        "aqp_cli/tests/",
        "aqp_bots/tests/",
        "aqp_rl/tests/",
        "aqp_models/tests/",
        "aqp_ingest/tests/",
        "aqp_ratelimit/tests/",
        "aqp_kernels/tests/",
        "aqp_ide/tests/",
        "aqp_snippets/tests/",
        "aqp_index/tests/",
        "AGENTS.md",
        "WORKFLOW.md",
        "RESTRUCTURING_PLAN.md",
        "README.md",
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
        "dist",
        "build",
    }
)

# Extensions we scan. Source files only; the topology YAML is exempt
# anyway via the prefix list.
TEXT_EXTENSIONS: frozenset[str] = frozenset(
    {".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".yaml", ".yml", ".sh", ".env"}
)

# Cluster-local service URL pattern: must contain a dotted suffix that
# ends in `.svc.cluster.local` (with or without a port / scheme).
_SVC_RE = re.compile(
    r"\b[a-z0-9][a-z0-9-]*\.[a-z0-9][a-z0-9-]*\.svc\.cluster\.local\b",
    re.IGNORECASE,
)


sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
from _lint_allowlist import filter_violations, normalise_path  # noqa: E402


def _is_exempt(rel_path: str) -> bool:
    return any(rel_path == p or rel_path.startswith(p) for p in EXEMPT_PREFIXES)


def _scan_file(path: Path) -> list[tuple[int, str]]:
    try:
        source = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(source.splitlines(), 1):
        m = _SVC_RE.search(line)
        if m:
            hits.append((lineno, m.group(0)))
    return hits


def _iter_files() -> list[Path]:
    out: list[Path] = []
    for p in REPO_ROOT.rglob("*"):
        if not p.is_file():
            continue
        if SKIP_PARTS & set(p.parts):
            continue
        if p.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        out.append(p)
    return out


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

    filtered = filter_violations(raw, "no_hardcoded_svc_urls")
    if filtered:
        print(
            "[no-hardcoded-svc-urls] FAIL: hardcoded "
            "`*.svc.cluster.local` URL outside the topology service."
        )
        print(
            "Replace with `topology.service_url(...)` (Rule 47). Cell "
            "routing requires per-tenant service URL resolution; "
            "hardcoded cluster-local URLs are not relocatable.\n"
            "Allowlist with a Phase-2 deadline in "
            "scripts/ci/allowlists/no_hardcoded_svc_urls.txt if this "
            "is a documented exception (e.g. bootstrap-only).\n"
        )
        for _, message in filtered:
            print(f"  - {message}")
        return 1
    print(
        f"[no-hardcoded-svc-urls] OK: scanned {len(files)} files, "
        f"{len(raw)} raw match(es), 0 unallowlisted."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
