"""Second-pass link rewriter for the migrated docs.

After ``migrate-content.py`` moves the 171 source files into the
new Diátaxis tree, the relative links INSIDE each doc still point
at the old shape. For example a doc that was at
``aqp_docs/architecture.md`` linking to ``operations/local-setup.md``
now lives at ``aqp_docs/docs/concepts/platform/architecture.md`` —
the new relative path is
``../../how-to/operations/local-setup.md``.

This script walks every ``.md`` and ``.mdx`` file under
``aqp_docs/docs/`` and rewrites:

  - ``operations/<slug>.md`` -> ``how-to/operations/<slug>.md``
  - ``runbooks/<slug>.md`` -> ``how-to/runbooks/<slug>.md``
  - ``mlops/<slug>.md`` -> ``how-to/mlops/<slug>.md``
  - ``architecture/<slug>.md`` -> ``architecture/<slug>.md``
    (unchanged, but the relative depth adjusts)
  - ``<slug>.md`` (root concept doc) ->
    ``concepts/<subsystem>/<slug>.md``

…relative to the file's own location, so the link works after
Docusaurus's ``onBrokenLinks: 'throw'`` runs.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = REPO_ROOT / "aqp_docs" / "docs"

# Mirrors aqp_docs/scripts/sweep-links.py CONCEPT_TARGETS.
CONCEPT_TARGETS: dict[str, str] = {
    # platform
    **{slug: "concepts/platform" for slug in (
        "architecture", "erd", "class-diagram", "flows", "domain-model",
        "core-types", "repository-split", "aqp-monorepo-paths",
        "code-index-governance", "legacy-types-shim", "temporal-identifiers",
        "instrument-taxonomy", "scopes", "entity-registry",
        "entity-graph-services", "contingency-graphs", "experiments-tests",
        "ownership-graph", "local-platform",
    )},
    **{slug: "concepts/data" for slug in (
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
    )},
    **{slug: "concepts/strategy" for slug in (
        "analysis-framework", "analysis-lab", "analysis-flows", "analysis-agents",
        "factor-research", "ml-framework", "ml-libraries", "ml-alpha-backtest",
        "ml-flows", "ml-preprocessing-pipeline", "ml-builder", "ml-testing",
        "backtest-engines", "vbtpro-integration", "hft-backtest", "optimal-control",
        "portfolio-options-mm", "microstructure-toxicity", "strategy-lifecycle",
        "strategy-browser", "strategy-development", "strategy-templates",
        "predictor-hub", "execution-paths", "cross-market-arbitrage",
        "statistical-arbitrage",
    )},
    **{slug: "concepts/rl" for slug in (
        "rl-framework", "rl-lab", "rl-components", "rl-iceberg",
        "rl-policy-backbones", "rl-market-dynamics", "rl-finagent",
        "rl-prudex-evaluation", "agentic-rl", "weight-centric-pipeline",
    )},
    **{slug: "concepts/agentic" for slug in (
        "agentic-development", "agentic-pipeline", "agents",
        "multi-agent-patterns", "workflow-studio", "orchestration-refactor-rollout",
        "alpha-researcher-agent", "research-agents", "trader-agents",
        "selection-agents", "bots",
    )},
    **{slug: "concepts/trading" for slug in (
        "paper-trading", "paper-metadata-gate", "observability",
        "observability-stack", "webui",
    )},
    **{slug: "concepts/identity" for slug in (
        "identity", "account-management", "credentials", "cloud-credentials",
        "auth0-setup", "auth0-actions", "auth0-microsoft-federation",
        "msal-entra-setup", "scim-provisioning", "multi-tenancy",
        "management-engine",
    )},
    **{slug: "concepts/infrastructure" for slug in (
        "aqp-ide", "aqp-ide-roadmap", "kubernetes-adapter",
        "kubernetes-rpi-deployment", "control-plane-topology",
        "terraform-control-plane", "iac-runbook",
    )},
}

# Where each top-level subdir lands.
SUBDIR_TARGETS = {
    "operations": "how-to/operations",
    "runbooks": "how-to/runbooks",
    "mlops": "how-to/mlops",
}

# Patterns that fire LOCALLY (per-file).
# Group 1: full match including the markdown link prefix.
# We match markdown links like [text](path.md) and bare path
# strings inside paragraphs (limited).
MD_LINK_RE = re.compile(r"\]\((?!https?:|/|#)([^)]+?\.mdx?)(#[^)]*)?\)")


def _new_route(slug: str) -> str | None:
    if slug in CONCEPT_TARGETS:
        return f"{CONCEPT_TARGETS[slug]}/{slug}"
    if slug == "index":
        return "intro/index"
    if slug == "glossary":
        return "intro/glossary"
    if slug == "installation":
        return "intro/installation"
    if slug == "data-dictionary":
        return "reference/data-dictionary/index"
    return None


def _resolve_link(file_route: str, link: str) -> str | None:
    """Map a legacy relative link to a NEW relative link.

    `file_route` is the source file's route relative to DOCS_DIR
    (e.g. `concepts/platform/architecture`).
    `link` is the legacy relative path (e.g. `operations/local-setup.md`
    or `bots.md` or `data-plane.md`).
    """
    # Drop the .md extension for route arithmetic.
    if link.endswith(".mdx"):
        target = link[:-4]
        ext = ".mdx"
    elif link.endswith(".md"):
        target = link[:-3]
        ext = ".md"
    else:
        return None

    target = target.lstrip("./")

    # Detect the subdir form first.
    parts = target.split("/", 1)
    new_target: str | None = None
    if len(parts) == 2 and parts[0] in SUBDIR_TARGETS:
        new_target = f"{SUBDIR_TARGETS[parts[0]]}/{parts[1]}"
    elif len(parts) == 2 and parts[0] == "architecture":
        new_target = f"architecture/{parts[1]}"
    elif len(parts) == 2 and parts[0] == "archive":
        new_target = f"archive/{parts[1]}"
    elif len(parts) == 1:
        # Single-token slug = root concept doc.
        new_target = _new_route(parts[0])

    if new_target is None:
        return None

    # Compute the new RELATIVE path from this file's location.
    source_depth = len(file_route.split("/")) - 1
    up = "../" * source_depth
    return f"{up}{new_target}{ext}"


def _walk() -> int:
    n = 0
    for path in DOCS_DIR.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in {".md", ".mdx"}:
            continue
        rel_route = str(path.relative_to(DOCS_DIR)).replace("\\", "/").rsplit(".", 1)[0]
        text = path.read_text(encoding="utf-8")
        original = text

        def _sub(match: re.Match[str]) -> str:
            link = match.group(1)
            anchor = match.group(2) or ""
            new_link = _resolve_link(rel_route, link)
            if new_link is None:
                return match.group(0)
            return f"]({new_link}{anchor})"

        text = MD_LINK_RE.sub(_sub, text)
        if text != original:
            path.write_text(text, encoding="utf-8")
            n += 1
            print(f"  rewrote: {path.relative_to(REPO_ROOT)}")
    return n


def main() -> None:
    print("Rewriting internal relative links in aqp_docs/docs/ ...")
    n = _walk()
    print(f"Done — {n} file(s) updated.")


if __name__ == "__main__":
    main()
