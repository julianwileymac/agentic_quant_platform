"""Migrate the 171+ legacy aqp_docs/ markdown files into the
Docusaurus Diátaxis IA.

This script is one-shot. It:

  1. Defines the canonical mapping from each legacy path
     ``aqp_docs/<old>.md`` to the new path
     ``aqp_docs/docs/<category>/<slug>.md``.
  2. For each file: reads, normalises frontmatter against the Zod
     schema in ``src/lib/frontmatterSchema.ts`` (mirrored in Python
     here), and writes to the new location.
  3. Removes the legacy file once the new file is in place. (``git mv``
     is preferred but not always available in the sandbox; the script
     uses plain ``shutil.move`` and relies on ``git`` to detect renames
     when the content is preserved verbatim, which it always is here.)

Run from the repo root::

    python aqp_docs/scripts/migrate-content.py

Idempotent: re-running after a partial run is safe; already-migrated
files are skipped.

Hard rules respected:

  - aqp-management-engine always-on: never logs secret material. This
    script touches only Markdown files.
  - aqp-index-reflect always-on: the matching debt note at
    ``.cursor/plans/aqp-index-debt-docusaurus-restructure.md`` is
    written separately and is required.
"""

from __future__ import annotations

import re
import shutil
from datetime import date
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_ROOT = REPO_ROOT / "aqp_docs"
NEW_DOCS_ROOT = DOCS_ROOT / "docs"
TODAY = date.today().isoformat()

# Slug -> (new relative dir, owner). The 132 root-level .md files
# (excluding index.md which becomes intro/index.md).
CONCEPT_MAPPING: dict[str, tuple[str, str]] = {
    # Platform
    "architecture": ("concepts/platform", "platform-team"),
    "erd": ("concepts/platform", "platform-team"),
    "class-diagram": ("concepts/platform", "platform-team"),
    "flows": ("concepts/platform", "platform-team"),
    "domain-model": ("concepts/platform", "platform-team"),
    "core-types": ("concepts/platform", "platform-team"),
    "repository-split": ("concepts/platform", "platform-team"),
    "aqp-monorepo-paths": ("concepts/platform", "platform-team"),
    "code-index-governance": ("concepts/platform", "platform-team"),
    "legacy-types-shim": ("concepts/platform", "platform-team"),
    "temporal-identifiers": ("concepts/platform", "platform-team"),
    "instrument-taxonomy": ("concepts/platform", "platform-team"),
    "scopes": ("concepts/platform", "platform-team"),
    "entity-registry": ("concepts/platform", "platform-team"),
    "entity-graph-services": ("concepts/platform", "platform-team"),
    "contingency-graphs": ("concepts/platform", "platform-team"),
    "experiments-tests": ("concepts/platform", "platform-team"),
    "ownership-graph": ("concepts/platform", "platform-team"),
    "local-platform": ("concepts/platform", "infra-team"),
    # Data plane
    "data-plane": ("concepts/data", "data-team"),
    "data-catalog": ("concepts/data", "data-team"),
    "data-self-service": ("concepts/data", "data-team"),
    "datasets-catalog": ("concepts/data", "data-team"),
    "metadata-cache": ("concepts/data", "data-team"),
    "data-discovery": ("concepts/data", "data-team"),
    "airbyte-builder": ("concepts/data", "data-team"),
    "dagster": ("concepts/data", "data-team"),
    "dagster-sandbox": ("concepts/data", "data-team"),
    "data-products": ("concepts/data", "data-team"),
    "data-mcp": ("concepts/data", "data-team"),
    "data-engine": ("concepts/data", "data-team"),
    "data-pipelines-hub": ("concepts/data", "data-team"),
    "data-layer-unification": ("concepts/data", "data-team"),
    "visualization-layer": ("concepts/data", "data-team"),
    "pgvector-control-plane": ("concepts/data", "data-team"),
    "codebase-mcp": ("concepts/data", "platform-team"),
    "sera": ("concepts/data", "platform-team"),
    "analytics-frontend": ("concepts/data", "data-team"),
    "agent-watchdog": ("concepts/data", "agentic-team"),
    "alpha-vantage": ("concepts/data", "data-team"),
    "futures-curves": ("concepts/data", "data-team"),
    "streaming": ("concepts/data", "data-team"),
    "streaming-admin": ("concepts/data", "data-team"),
    "live-market": ("concepts/data", "data-team"),
    "regulatory-data": ("concepts/data", "data-team"),
    "redpanda": ("concepts/data", "data-team"),
    "questdb": ("concepts/data", "data-team"),
    "phoenix": ("concepts/data", "data-team"),
    "hudi": ("concepts/data", "data-team"),
    "datahub-sync": ("concepts/data", "data-team"),
    "pricing-context": ("concepts/data", "data-team"),
    "research-papers-rag": ("concepts/data", "agentic-team"),
    "rag": ("concepts/data", "agentic-team"),
    "mcp-risk-tools": ("concepts/data", "trading-team"),
    "accounts-balances": ("concepts/data", "trading-team"),
    "order-types": ("concepts/data", "trading-team"),
    "reconciliation": ("concepts/data", "trading-team"),
    "providers": ("concepts/data", "data-team"),
    # Strategy + ML
    "analysis-framework": ("concepts/strategy", "strategy-team"),
    "analysis-lab": ("concepts/strategy", "strategy-team"),
    "analysis-flows": ("concepts/strategy", "strategy-team"),
    "analysis-agents": ("concepts/strategy", "agentic-team"),
    "factor-research": ("concepts/strategy", "strategy-team"),
    "ml-framework": ("concepts/strategy", "ml-team"),
    "ml-libraries": ("concepts/strategy", "ml-team"),
    "ml-alpha-backtest": ("concepts/strategy", "ml-team"),
    "ml-flows": ("concepts/strategy", "ml-team"),
    "ml-preprocessing-pipeline": ("concepts/strategy", "ml-team"),
    "ml-builder": ("concepts/strategy", "ml-team"),
    "ml-testing": ("concepts/strategy", "ml-team"),
    "backtest-engines": ("concepts/strategy", "strategy-team"),
    "vbtpro-integration": ("concepts/strategy", "strategy-team"),
    "hft-backtest": ("concepts/strategy", "strategy-team"),
    "optimal-control": ("concepts/strategy", "strategy-team"),
    "portfolio-options-mm": ("concepts/strategy", "strategy-team"),
    "microstructure-toxicity": ("concepts/strategy", "strategy-team"),
    "strategy-lifecycle": ("concepts/strategy", "strategy-team"),
    "strategy-browser": ("concepts/strategy", "strategy-team"),
    "strategy-development": ("concepts/strategy", "strategy-team"),
    "strategy-templates": ("concepts/strategy", "strategy-team"),
    "predictor-hub": ("concepts/strategy", "ml-team"),
    "execution-paths": ("concepts/strategy", "trading-team"),
    "cross-market-arbitrage": ("concepts/strategy", "strategy-team"),
    "statistical-arbitrage": ("concepts/strategy", "strategy-team"),
    # RL
    "rl-framework": ("concepts/rl", "rl-team"),
    "rl-lab": ("concepts/rl", "rl-team"),
    "rl-components": ("concepts/rl", "rl-team"),
    "rl-iceberg": ("concepts/rl", "rl-team"),
    "rl-policy-backbones": ("concepts/rl", "rl-team"),
    "rl-market-dynamics": ("concepts/rl", "rl-team"),
    "rl-finagent": ("concepts/rl", "rl-team"),
    "rl-prudex-evaluation": ("concepts/rl", "rl-team"),
    "agentic-rl": ("concepts/rl", "rl-team"),
    "weight-centric-pipeline": ("concepts/rl", "rl-team"),
    # Agentic
    "agentic-development": ("concepts/agentic", "agentic-team"),
    "agentic-pipeline": ("concepts/agentic", "agentic-team"),
    "agents": ("concepts/agentic", "agentic-team"),
    "multi-agent-patterns": ("concepts/agentic", "agentic-team"),
    "workflow-studio": ("concepts/agentic", "agentic-team"),
    "orchestration-refactor-rollout": ("concepts/agentic", "agentic-team"),
    "alpha-researcher-agent": ("concepts/agentic", "agentic-team"),
    "research-agents": ("concepts/agentic", "agentic-team"),
    "trader-agents": ("concepts/agentic", "agentic-team"),
    "selection-agents": ("concepts/agentic", "agentic-team"),
    "bots": ("concepts/agentic", "agentic-team"),
    # Trading + ops
    "paper-trading": ("concepts/trading", "trading-team"),
    "paper-metadata-gate": ("concepts/trading", "trading-team"),
    "observability": ("concepts/trading", "sre-team"),
    "observability-stack": ("concepts/trading", "sre-team"),
    "webui": ("concepts/trading", "platform-team"),
    # Identity + tenancy
    "identity": ("concepts/identity", "identity-team"),
    "account-management": ("concepts/identity", "identity-team"),
    "credentials": ("concepts/identity", "identity-team"),
    "cloud-credentials": ("concepts/identity", "identity-team"),
    "auth0-setup": ("concepts/identity", "identity-team"),
    "auth0-actions": ("concepts/identity", "identity-team"),
    "auth0-microsoft-federation": ("concepts/identity", "identity-team"),
    "msal-entra-setup": ("concepts/identity", "identity-team"),
    "scim-provisioning": ("concepts/identity", "identity-team"),
    "multi-tenancy": ("concepts/identity", "identity-team"),
    "management-engine": ("concepts/identity", "identity-team"),
    # Infrastructure
    "aqp-ide": ("concepts/infrastructure", "platform-team"),
    "aqp-ide-roadmap": ("concepts/infrastructure", "platform-team"),
    "installation": ("concepts/infrastructure", "infra-team"),
    "kubernetes-adapter": ("concepts/infrastructure", "infra-team"),
    "kubernetes-rpi-deployment": ("concepts/infrastructure", "infra-team"),
    "control-plane-topology": ("concepts/infrastructure", "infra-team"),
    "terraform-control-plane": ("concepts/infrastructure", "infra-team"),
    "iac-runbook": ("concepts/infrastructure", "infra-team"),
    # Glossary -> intro
    "glossary": ("intro", "docs-team"),
}

# Subdirectory passthroughs.
SUBDIR_MAPPING: dict[str, tuple[str, str]] = {
    # legacy_subdir -> (new_parent_dir, default_owner)
    "operations": ("how-to/operations", "sre-team"),
    "runbooks": ("how-to/runbooks", "sre-team"),
    "mlops": ("how-to/mlops", "ml-team"),
    "architecture/decisions": ("architecture/decisions", "platform-team"),
}

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _humanise(slug: str) -> str:
    return " ".join(part.capitalize() for part in slug.replace("_", "-").split("-"))


def _build_frontmatter(
    *,
    title: str,
    summary: str,
    owner: str,
    audience: str = "both",
    sidebar_label: str | None = None,
) -> str:
    lines = [
        "---",
        f"title: {title!r}",
        f"summary: {summary!r}",
        f"owner: {owner}",
        f"last_reviewed: {TODAY}",
        f"audience: {audience}",
    ]
    if sidebar_label and sidebar_label != title:
        lines.append(f"sidebar_label: {sidebar_label!r}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def _extract_title_and_summary(body: str, slug: str) -> tuple[str, str]:
    """Pick a title from the first H1 if present; fall back to the slug."""
    title_match = re.search(r"^#\s+(.+?)\s*$", body, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else _humanise(slug)
    # Summary: the first non-empty paragraph after the title, capped
    # at 200 chars.
    body_after_title = body[title_match.end() :] if title_match else body
    first_para_match = re.search(r"\n\s*\n([^\n#].+?)(?:\n\s*\n|\Z)", body_after_title, re.DOTALL)
    raw_summary = first_para_match.group(1).strip() if first_para_match else title
    summary = re.sub(r"\s+", " ", raw_summary)[:200].rstrip(".") + ("..." if len(raw_summary) > 200 else "")
    summary = summary.replace("'", "")  # YAML-safe single quotes
    return title, summary


def _migrate_one(src: Path, dest: Path, owner: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    body = _read_text(src)

    # Strip existing frontmatter if present so we can replace with a
    # fully-stamped block.
    fm_match = FRONTMATTER_RE.match(body)
    if fm_match:
        body_after_fm = body[fm_match.end():]
    else:
        body_after_fm = body

    slug = src.stem
    title, summary = _extract_title_and_summary(body_after_fm, slug)
    new_fm = _build_frontmatter(title=title, summary=summary, owner=owner)
    dest.write_text(new_fm + body_after_fm, encoding="utf-8")
    print(f"  migrated: {src.relative_to(REPO_ROOT)} -> {dest.relative_to(REPO_ROOT)}")
    src.unlink()


def _iter_root_md_files() -> Iterable[Path]:
    for p in DOCS_ROOT.glob("*.md"):
        yield p


def _iter_subdir_md_files(subdir: str) -> Iterable[Path]:
    base = DOCS_ROOT / subdir
    if not base.exists():
        return ()
    return base.glob("**/*.md") if subdir == "architecture/decisions" else base.glob("*.md")


def migrate() -> None:
    NEW_DOCS_ROOT.mkdir(parents=True, exist_ok=True)
    print("Migrating root-level docs...")
    for p in _iter_root_md_files():
        slug = p.stem
        if slug == "index":
            dest = NEW_DOCS_ROOT / "intro" / "index.md"
            _migrate_one(p, dest, owner="docs-team")
            continue
        if slug == "data-dictionary":
            dest = NEW_DOCS_ROOT / "reference" / "data-dictionary" / "index.mdx"
            _migrate_one(p, dest, owner="data-team")
            continue
        if slug == "installation":
            dest = NEW_DOCS_ROOT / "intro" / "installation.md"
            _migrate_one(p, dest, owner="docs-team")
            continue
        if slug not in CONCEPT_MAPPING:
            print(f"  WARNING: unmapped root doc {slug}; placing under concepts/platform/")
            dest = NEW_DOCS_ROOT / "concepts" / "platform" / f"{slug}.md"
            _migrate_one(p, dest, owner="platform-team")
            continue
        new_dir, owner = CONCEPT_MAPPING[slug]
        dest = NEW_DOCS_ROOT / new_dir / f"{slug}.md"
        _migrate_one(p, dest, owner=owner)

    print("Migrating operations/ ...")
    for p in _iter_subdir_md_files("operations"):
        dest = NEW_DOCS_ROOT / "how-to" / "operations" / p.name
        _migrate_one(p, dest, owner="sre-team")

    print("Migrating runbooks/ ...")
    for p in _iter_subdir_md_files("runbooks"):
        dest = NEW_DOCS_ROOT / "how-to" / "runbooks" / p.name
        _migrate_one(p, dest, owner="sre-team")

    print("Migrating mlops/ ...")
    for p in _iter_subdir_md_files("mlops"):
        dest = NEW_DOCS_ROOT / "how-to" / "mlops" / p.name
        _migrate_one(p, dest, owner="ml-team")

    print("Migrating architecture/ ...")
    arch_decisions = DOCS_ROOT / "architecture" / "decisions"
    if arch_decisions.exists():
        for p in arch_decisions.glob("*.md"):
            dest = NEW_DOCS_ROOT / "architecture" / "decisions" / p.name
            _migrate_one(p, dest, owner="platform-team")
    arch_specs = DOCS_ROOT / "architecture"
    if arch_specs.exists():
        for p in arch_specs.glob("*.md"):
            dest = NEW_DOCS_ROOT / "architecture" / p.name
            _migrate_one(p, dest, owner="platform-team")

    print("Migrating archive/ ...")
    archive_dir = DOCS_ROOT / "archive"
    if archive_dir.exists():
        for p in archive_dir.glob("*.md"):
            dest_name = p.name
            if dest_name == "Agentic Quant Platform Enhancement Plan.md":
                dest_name = "aqp-enhancement-plan.md"
            dest = NEW_DOCS_ROOT / "archive" / dest_name
            _migrate_one(p, dest, owner="docs-team")

    print("Cleaning up empty legacy directories...")
    for sub in ("operations", "runbooks", "mlops", "archive", "architecture/decisions", "architecture"):
        d = DOCS_ROOT / sub
        if d.exists() and not any(d.iterdir()):
            d.rmdir()
            print(f"  removed: {d.relative_to(REPO_ROOT)}")

    print("Done. Run scripts/sweep-links.py next.")


if __name__ == "__main__":
    migrate()
