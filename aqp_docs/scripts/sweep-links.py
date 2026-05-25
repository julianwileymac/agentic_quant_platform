"""Rewrite every legacy ``aqp_docs/<path>.md`` reference repo-wide.

After ``migrate-content.py`` has shifted the 171 markdown files into
``aqp_docs/docs/<category>/<slug>.md``, this script sweeps the
ancillary files that reference them by relative path:

  - ``AGENTS.md`` (repo root)
  - every file under ``.cursor/rules/``
  - every ``aqp_*/AGENTS.md``
  - ``CONTRIBUTING.md``, ``WORKFLOW.md``, ``README.md``
  - Python docstring comments (best-effort) under ``aqp/``,
    ``aqp_control_plane/src/``, ``aqp_platform_core/src/``,
    ``aqp_rl/src/``, ``aqp_models/src/``

What it does NOT touch:

  - ``aqp_index/**`` — sole-writer boundary per
    ``.cursor/rules/aqp-index.mdc``. The matching debt note at
    ``.cursor/plans/aqp-index-debt-docusaurus-restructure.md``
    triggers the curator's next pass.

Run from repo root::

    python aqp_docs/scripts/sweep-links.py
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]

# (legacy_relative_path, new_relative_path) pairs. Both are relative
# to the repo root and DO NOT include leading ``./``.
LEGACY_TO_NEW: dict[str, str] = {
    "aqp_docs/index.md": "aqp_docs/docs/intro/index.md",
    "aqp_docs/data-dictionary.md": "aqp_docs/docs/reference/data-dictionary/index.mdx",
    "aqp_docs/installation.md": "aqp_docs/docs/intro/installation.md",
    "aqp_docs/glossary.md": "aqp_docs/docs/intro/glossary.md",
    # Subdir passthroughs handled via dynamic prefix rules below.
}

# Dynamic prefix replacement (longest-first to avoid overlap).
PREFIX_RULES: list[tuple[str, str]] = [
    ("aqp_docs/architecture/decisions/", "aqp_docs/docs/architecture/decisions/"),
    ("aqp_docs/architecture/", "aqp_docs/docs/architecture/"),
    ("aqp_docs/operations/", "aqp_docs/docs/how-to/operations/"),
    ("aqp_docs/runbooks/", "aqp_docs/docs/how-to/runbooks/"),
    ("aqp_docs/mlops/", "aqp_docs/docs/how-to/mlops/"),
    ("aqp_docs/archive/Agentic Quant Platform Enhancement Plan.md",
     "aqp_docs/docs/archive/aqp-enhancement-plan.md"),
    ("aqp_docs/archive/", "aqp_docs/docs/archive/"),
]

# Concept slug -> new subdir, mirrors migrate-content.py.
CONCEPT_TARGETS: dict[str, str] = {
    # platform
    **{
        slug: "concepts/platform"
        for slug in (
            "architecture", "erd", "class-diagram", "flows", "domain-model",
            "core-types", "repository-split", "aqp-monorepo-paths",
            "code-index-governance", "legacy-types-shim", "temporal-identifiers",
            "instrument-taxonomy", "scopes", "entity-registry",
            "entity-graph-services", "contingency-graphs", "experiments-tests",
            "ownership-graph", "local-platform",
        )
    },
    # data
    **{
        slug: "concepts/data"
        for slug in (
            "data-plane", "data-catalog", "data-self-service", "datasets-catalog",
            "metadata-cache", "data-discovery", "airbyte-builder", "dagster",
            "dagster-sandbox", "data-products", "data-mcp", "data-engine",
            "data-pipelines-hub", "data-layer-unification", "visualization-layer",
            "pgvector-control-plane", "codebase-mcp", "sera", "analytics-frontend",
            "agent-watchdog", "alpha-vantage", "futures-curves", "streaming",
            "streaming-admin", "live-market", "regulatory-data", "redpanda",
            "questdb", "phoenix", "hudi", "datahub-sync", "pricing-context",
            "research-papers-rag", "rag", "mcp-risk-tools", "accounts-balances",
            "order-types", "reconciliation", "providers",
        )
    },
    # strategy
    **{
        slug: "concepts/strategy"
        for slug in (
            "analysis-framework", "analysis-lab", "analysis-flows", "analysis-agents",
            "factor-research", "ml-framework", "ml-libraries", "ml-alpha-backtest",
            "ml-flows", "ml-preprocessing-pipeline", "ml-builder", "ml-testing",
            "backtest-engines", "vbtpro-integration", "hft-backtest", "optimal-control",
            "portfolio-options-mm", "microstructure-toxicity", "strategy-lifecycle",
            "strategy-browser", "strategy-development", "strategy-templates",
            "predictor-hub", "execution-paths", "cross-market-arbitrage",
            "statistical-arbitrage",
        )
    },
    # rl
    **{
        slug: "concepts/rl"
        for slug in (
            "rl-framework", "rl-lab", "rl-components", "rl-iceberg",
            "rl-policy-backbones", "rl-market-dynamics", "rl-finagent",
            "rl-prudex-evaluation", "agentic-rl", "weight-centric-pipeline",
        )
    },
    # agentic
    **{
        slug: "concepts/agentic"
        for slug in (
            "agentic-development", "agentic-pipeline", "agents",
            "multi-agent-patterns", "workflow-studio", "orchestration-refactor-rollout",
            "alpha-researcher-agent", "research-agents", "trader-agents",
            "selection-agents", "bots",
        )
    },
    # trading
    **{
        slug: "concepts/trading"
        for slug in (
            "paper-trading", "paper-metadata-gate", "observability",
            "observability-stack", "webui",
        )
    },
    # identity
    **{
        slug: "concepts/identity"
        for slug in (
            "identity", "account-management", "credentials", "cloud-credentials",
            "auth0-setup", "auth0-actions", "auth0-microsoft-federation",
            "msal-entra-setup", "scim-provisioning", "multi-tenancy",
            "management-engine",
        )
    },
    # infrastructure
    **{
        slug: "concepts/infrastructure"
        for slug in (
            "aqp-ide", "aqp-ide-roadmap", "kubernetes-adapter",
            "kubernetes-rpi-deployment", "control-plane-topology",
            "terraform-control-plane", "iac-runbook",
        )
    },
}

# Files to sweep, relative to repo root.
SWEEP_TARGETS: list[Path] = []


# Sole-writer trees we MUST never touch. See:
#   - .cursor/rules/aqp-index.mdc
#   - aqp_index/AGENTS.md
SOLE_WRITER_DIRS = {"aqp_index"}


def _under_sole_writer(path: Path) -> bool:
    """Return True if `path` lives anywhere under a sole-writer tree."""
    parts = path.relative_to(REPO_ROOT).parts
    return any(p in SOLE_WRITER_DIRS for p in parts)


def _enumerate_sweep_targets() -> list[Path]:
    targets: list[Path] = []
    for p in (REPO_ROOT / "AGENTS.md",
              REPO_ROOT / "CONTRIBUTING.md",
              REPO_ROOT / "WORKFLOW.md",
              REPO_ROOT / "README.md"):
        if p.exists():
            targets.append(p)
    rules_dir = REPO_ROOT / ".cursor" / "rules"
    if rules_dir.exists():
        targets.extend(rules_dir.rglob("*.mdc"))
        targets.extend(rules_dir.rglob("*.md"))
    agents_dir = REPO_ROOT / ".cursor" / "agents"
    if agents_dir.exists():
        targets.extend(agents_dir.rglob("*.md"))
    # Every aqp_* tree (AGENTS.md + README.md) — not just AGENTS.md, so
    # that aqp_admin/README.md etc. also get swept.
    for sub in REPO_ROOT.glob("aqp_*"):
        if sub.is_dir():
            for name in ("AGENTS.md", "README.md", "CUTOVER.md"):
                f = sub / name
                if f.exists():
                    targets.append(f)
    # GitHub-side metadata.
    gh_dir = REPO_ROOT / ".github"
    if gh_dir.exists():
        targets.append(gh_dir / "CODEOWNERS") if (gh_dir / "CODEOWNERS").exists() else None
    # Python source under the runtime packages, plus all under aqp_*/src.
    # We sweep these because docstrings cite the docs tree.
    python_roots = [
        REPO_ROOT / "aqp",
        REPO_ROOT / "aqp_control_plane" / "src",
        REPO_ROOT / "aqp_platform_core" / "src",
        REPO_ROOT / "aqp_rl" / "src",
        REPO_ROOT / "aqp_models" / "src",
        REPO_ROOT / "aqp_bots",
        REPO_ROOT / "aqp_cli" / "src",
        REPO_ROOT / "aqp_admin" / "src",
        REPO_ROOT / "scripts",
    ]
    for root in python_roots:
        if root.exists():
            for py in root.rglob("*.py"):
                # Skip __pycache__ and any vendored / generated trees.
                if "__pycache__" in py.parts or ".venv" in py.parts:
                    continue
                targets.append(py)
    # AGENTS.md inside aqp/* nested packages.
    for ag in REPO_ROOT.glob("aqp/**/AGENTS.md"):
        targets.append(ag)
    # Frontend client trees — CUTOVER, READMEs, and .env.example files
    # often reference docs.
    for client_tree in ("aqp_client", "aqp_ui", "aqp_admin", "webui"):
        c = REPO_ROOT / client_tree
        if c.exists():
            for name in ("README.md", "CUTOVER.md", ".env.example"):
                f = c / name
                if f.exists():
                    targets.append(f)
    # YAML configs that reference docs.
    configs_dir = REPO_ROOT / "configs"
    if configs_dir.exists():
        targets.extend(configs_dir.rglob("*.yaml"))
        targets.extend(configs_dir.rglob("*.yml"))
    # Plan + debt-note files that aren't the curator's debt notes.
    plans_dir = REPO_ROOT / ".cursor" / "plans"
    if plans_dir.exists():
        for plan in plans_dir.rglob("*.md"):
            # Skip aqp-index-debt notes (Phase 0 specifically opens
            # one + others may be in flight from other curator runs).
            if plan.name.startswith("aqp-index-debt-"):
                continue
            targets.append(plan)
    # Sibling package docs (aqp_ide/docs, aqp_cli/docs etc.) and the
    # platform/admin docs trees + theia-extensions READMEs.
    for trees in (
        "aqp_ide/docs",
        "aqp_ide/theia-extensions",
        "aqp_ide/applications",
        "aqp_cli/docs",
        "aqp_platform/deployments",
        "aqp_platform/scripts",
        "aqp_platform/terraform",
        "aqp_platform/flink-jobs",
        "aqp_platform/deploy",
    ):
        td = REPO_ROOT / trees
        if td.exists():
            targets.extend(td.rglob("*.md"))
    # Shell scripts under aqp_platform/scripts/ reference docs paths.
    for sh in (REPO_ROOT / "aqp_platform" / "scripts").rglob("*.sh"):
        targets.append(sh)
    # Dockerfile variants outside the standard frontend trees (aqp_ide
    # has its own Dockerfiles citing docs in comments).
    for ide_dock in (REPO_ROOT / "aqp_ide").rglob("*Dockerfile"):
        targets.append(ide_dock)
    # Sibling Cursor rule trees (e.g., aqp_ide/.cursor/...).
    for nested_cursor in REPO_ROOT.glob("aqp_*/.cursor/**"):
        if nested_cursor.is_file() and nested_cursor.suffix in {".mdc", ".md"}:
            targets.append(nested_cursor)
    # INDEX.md / README.md inside any aqp_* tree at any depth.
    for sub in REPO_ROOT.glob("aqp_*"):
        if sub.is_dir():
            for name in ("INDEX.md", "MIGRATION.md", "DEFERRED.md"):
                for f in sub.rglob(name):
                    targets.append(f)
    # Tests that lean on docstring references.
    tests_dir = REPO_ROOT / "tests"
    if tests_dir.exists():
        for py in tests_dir.rglob("*.py"):
            if "__pycache__" in py.parts:
                continue
            targets.append(py)
    # Top-level repo metadata files.
    for top in ("Makefile", "pyproject.toml", ".env.example", ".gitignore"):
        f = REPO_ROOT / top
        if f.exists():
            targets.append(f)
    # Frontend source trees with TSX/TS docstring references.
    for client_tree in ("aqp_client", "aqp_ui", "aqp_admin"):
        c_src = REPO_ROOT / client_tree / "src"
        if c_src.exists():
            for ext in ("*.ts", "*.tsx", "*.js", "*.jsx"):
                for f in c_src.rglob(ext):
                    if "node_modules" in f.parts or ".next" in f.parts or "build" in f.parts:
                        continue
                    targets.append(f)
        # Dockerfile + .Dockerfile variants.
        for f in (REPO_ROOT / client_tree).rglob("*Dockerfile"):
            targets.append(f)
    # Yaml / yml outside configs (already covered) — eg. kubernetes
    # manifest annotations that cite docs.
    for tree in ("aqp_platform/deployments", "aqp_platform/configs"):
        td = REPO_ROOT / tree
        if td.exists():
            for ext in ("*.yaml", "*.yml"):
                for f in td.rglob(ext):
                    targets.append(f)
    # Cursor research trees.
    research_dir = REPO_ROOT / ".cursor" / "research"
    if research_dir.exists():
        for f in research_dir.rglob("*.md"):
            targets.append(f)
    # Deduplicate while preserving order AND drop anything inside a
    # sole-writer tree (aqp_index/** etc.). The earlier per-loop
    # filters are best-effort; this is the final hard gate.
    seen: set[Path] = set()
    deduped: list[Path] = []
    for t in targets:
        if t is None:
            continue
        rp = t.resolve()
        if rp in seen:
            continue
        try:
            if _under_sole_writer(t):
                continue
        except ValueError:
            # path is outside REPO_ROOT — also skip defensively
            continue
        seen.add(rp)
        deduped.append(t)
    return deduped


def _rewrite_concept_links(text: str) -> str:
    """Rewrite ``aqp_docs/<slug>.md`` for every root-level slug into the
    new ``aqp_docs/docs/<category>/<slug>.md`` path."""
    def _sub(match: re.Match[str]) -> str:
        slug = match.group(1)
        if slug in CONCEPT_TARGETS:
            return f"aqp_docs/docs/{CONCEPT_TARGETS[slug]}/{slug}.md"
        if slug == "index":
            return "aqp_docs/docs/intro/index.md"
        if slug == "glossary":
            return "aqp_docs/docs/intro/glossary.md"
        if slug == "installation":
            return "aqp_docs/docs/intro/installation.md"
        if slug == "data-dictionary":
            return "aqp_docs/docs/reference/data-dictionary/index.mdx"
        # Unknown -> leave alone; reviewer follow-up.
        return match.group(0)

    # Match ``aqp_docs/<slug>.md`` where slug has no slash. Allow
    # surrounding parens / backticks / quotes for both Markdown and
    # Python docstring contexts.
    return re.sub(r"aqp_docs/([a-zA-Z0-9_-]+)\.md", _sub, text)


def _rewrite_prefix_rules(text: str) -> str:
    for old, new in PREFIX_RULES:
        text = text.replace(old, new)
    return text


def _rewrite_explicit(text: str) -> str:
    for old, new in LEGACY_TO_NEW.items():
        text = text.replace(old, new)
    return text


def _sweep_file(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    rewritten = _rewrite_concept_links(original)
    rewritten = _rewrite_prefix_rules(rewritten)
    rewritten = _rewrite_explicit(rewritten)
    if rewritten != original:
        path.write_text(rewritten, encoding="utf-8")
        return True
    return False


def main() -> None:
    targets = _enumerate_sweep_targets()
    print(f"Sweeping {len(targets)} files for legacy aqp_docs/ links...")
    changed = 0
    for p in targets:
        if _sweep_file(p):
            changed += 1
            print(f"  rewrote: {p.relative_to(REPO_ROOT)}")
    print(f"\n{changed} files rewritten.")
    print("\nReminder: aqp_index/** is intentionally NOT swept.")
    print("Sole-writer rule applies; the curator handles it on its next pass.")
    print("Debt note: .cursor/plans/aqp-index-debt-docusaurus-restructure.md")


if __name__ == "__main__":
    main()
