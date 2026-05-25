"""Rewrite relative markdown links that resolve OUTSIDE aqp_docs/docs/.

After the Phase 0 migration + internal-link rewriter, the only
remaining broken-link class is references to files outside the
Docusaurus content tree (AGENTS.md, README.md, CONTRIBUTING.md,
aqp_client/README.md, etc.). These work on GitHub but Docusaurus's
``onBrokenLinks: 'throw'`` rejects them at build time because they
do not map to a content route.

This script walks every ``.md`` / ``.mdx`` under ``aqp_docs/docs/``,
parses each relative link, and rewrites any link whose target lives
outside the docs tree to an absolute GitHub URL.

Idempotent. Safe to re-run.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = REPO_ROOT / "aqp_docs" / "docs"
REPO_URL = "https://github.com/julianwileymac/agentic_quant_platform/blob/main"

LINK_RE = re.compile(r"\]\((?!https?:|/|#|@|mailto:)([^)]+?\.mdx?)(#[^)]*)?\)")


# Known repo-root files contributors commonly reference with the wrong
# relative depth. Mapping the final basename to its canonical repo path
# avoids guessing at the author's intent.
KNOWN_REPO_FILES = {
    "AGENTS.md": "AGENTS.md",
    "WORKFLOW.md": "WORKFLOW.md",
    "CONTRIBUTING.md": "CONTRIBUTING.md",
    "README.md": "README.md",
    "AQP_REFACTOR_MASTER_PROMPT.md": "aqp_docs/docs/archive/AQP_REFACTOR_MASTER_PROMPT.md",
}


def _try_resolve_in_repo(path: Path, target: str) -> Path | None:
    """Resolve `target` against the repo root + a small set of likely
    bases. Returns the matching path inside the repo or None.
    """
    # Strip leading ./ segments (literal, not the lstrip-character-set
    # variant which over-stripped the leading dot of paths like
    # `../.cursor/plans/...`).
    cleaned = target
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    # Strip leading ../ segments (one at a time, literal).
    while cleaned.startswith("../"):
        cleaned = cleaned[3:]

    candidates = [
        REPO_ROOT / cleaned,
    ]
    # Swap .md for .mdx (we have a few index.mdx files referenced as .md).
    if cleaned.endswith(".md"):
        candidates.append(REPO_ROOT / (cleaned[:-3] + ".mdx"))
    basename = Path(cleaned).name
    if basename in KNOWN_REPO_FILES:
        candidates.append(REPO_ROOT / KNOWN_REPO_FILES[basename])
    for c in candidates:
        if c.exists():
            return c
    return None


def _rewrite_file(path: Path) -> int:
    """Return the number of links rewritten in `path`."""
    text = path.read_text(encoding="utf-8")
    changed = 0

    def _sub(match: re.Match[str]) -> str:
        nonlocal changed
        target = match.group(1)
        anchor = match.group(2) or ""
        try:
            resolved = (path.parent / target).resolve()
        except (OSError, ValueError):
            return match.group(0)
        # If it resolves to a real file inside the docs tree, leave alone.
        try:
            resolved.relative_to(DOCS_DIR)
            if resolved.exists():
                return match.group(0)
        except ValueError:
            pass
        # If it resolves to a real file inside the repo (but outside docs),
        # build a GitHub URL.
        if resolved.exists():
            try:
                repo_relative = resolved.relative_to(REPO_ROOT)
                changed += 1
                return f"]({REPO_URL}/{repo_relative.as_posix()}{anchor})"
            except ValueError:
                return match.group(0)
        # Resolved path does not exist. Try the salvage paths.
        salvage = _try_resolve_in_repo(path, target)
        if salvage is not None:
            try:
                repo_relative = salvage.relative_to(REPO_ROOT)
                changed += 1
                return f"]({REPO_URL}/{repo_relative.as_posix()}{anchor})"
            except ValueError:
                return match.group(0)
        return match.group(0)

    new_text = LINK_RE.sub(_sub, text)
    if changed:
        path.write_text(new_text, encoding="utf-8")
    return changed


def main() -> None:
    total_files = 0
    total_links = 0
    for path in DOCS_DIR.rglob("*"):
        if not path.is_file() or path.suffix not in {".md", ".mdx"}:
            continue
        n = _rewrite_file(path)
        if n:
            total_files += 1
            total_links += n
            print(f"  rewrote {n:>3} link(s) in {path.relative_to(REPO_ROOT)}")
    print(f"\nDone — {total_links} links across {total_files} files.")


if __name__ == "__main__":
    main()
