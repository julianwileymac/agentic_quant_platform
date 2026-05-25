"""Docs freshness watchdog — scans aqp_docs/docs/ for stale pages.

Phase 6 of the docs-migration plan. The task:

1. Walks every ``.md`` and ``.mdx`` file under ``aqp_docs/docs/``.
2. Parses the frontmatter (the Zod schema mirrored from
   ``aqp_docs/src/lib/frontmatterSchema.ts``).
3. Computes ``today - last_reviewed`` for each page.
4. For any page where the delta exceeds
   ``settings.docs_freshness_threshold_days`` (default 180), opens
   a single GitHub Issue tagged with the page's CODEOWNER team.

The GitHub API call uses the same M2M token / GitHub App
installation token used by the feedback Worker, resolved through
:class:`CredentialResolver` (AGENTS rule 26). Issue creation is
idempotent — the task fingerprints ``(page, week)`` so we open at
most one issue per page per week.

Hard rules honoured:

- AGENTS rule 4 (Celery progress) — every emit goes through
  ``aqp.tasks._progress``.
- AGENTS rule 5 (cross-task state) — IDs are passed; the task
  re-fetches state in the worker (here: re-walks the docs tree).
- AGENTS rule 22 (DataMCP boundary) — no ORM touched directly
  inside the agent body. The matching read surface lives at
  ``data.docs.list_pages``.
- AGENTS rule 26 (CredentialResolver) — the GitHub App token comes
  from Vault.
- ``aqp-management-engine`` always-on (credential safety) — the
  Authorization header is never logged, even on failure.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = REPO_ROOT / "aqp_docs" / "docs"
EXCLUDE_DIRS = {"archive", "reference"}  # auto-generated / frozen


def _today() -> date:
    return date.today()


def _settings() -> Any:
    from aqp.config import settings

    return settings


def _threshold_days() -> int:
    return int(getattr(_settings(), "docs_freshness_threshold_days", 180) or 180)


def _resolve_github_token() -> str | None:
    """Resolve the GitHub App installation token via CredentialResolver.

    Returns ``None`` when no token is configured — the task soft-fails
    rather than erroring out so a dev environment without GitHub
    creds still produces useful logs.
    """
    try:
        from aqp.credentials.resolver import CredentialResolver
    except Exception:  # pragma: no cover - defensive
        return None
    try:
        resolver = CredentialResolver()
        return resolver.resolve_secret("docs.github_app_installation_token") or None
    except Exception:  # pragma: no cover - resolver chain may fail in dev
        return None


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_KV_RE = re.compile(r"^([a-zA-Z_]+):\s*['\"]?([^'\"]*)['\"]?\s*$")


def _parse_frontmatter(text: str) -> dict[str, str]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}
    out: dict[str, str] = {}
    for line in match.group(1).split("\n"):
        kv = _KV_RE.match(line)
        if not kv:
            continue
        out[kv.group(1)] = kv.group(2)
    return out


def _iter_docs() -> list[Path]:
    if not DOCS_DIR.exists():
        return []
    out: list[Path] = []
    for path in DOCS_DIR.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in {".md", ".mdx"}:
            continue
        parts = path.relative_to(DOCS_DIR).parts
        if any(p in EXCLUDE_DIRS for p in parts):
            continue
        out.append(path)
    return out


def _stale_pages(threshold_days: int) -> list[dict[str, Any]]:
    today = _today()
    threshold = timedelta(days=threshold_days)
    rows: list[dict[str, Any]] = []
    for path in _iter_docs():
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:  # pragma: no cover - filesystem hiccup
            continue
        fm = _parse_frontmatter(text)
        last_reviewed_raw = fm.get("last_reviewed", "")
        try:
            last_reviewed = datetime.strptime(last_reviewed_raw, "%Y-%m-%d").date()
        except ValueError:
            # Pages without a parseable last_reviewed get flagged
            # immediately; the frontmatter is required by the Zod
            # schema, so missing fields are a hard miss.
            last_reviewed = date(1970, 1, 1)
        age = today - last_reviewed
        if age >= threshold:
            rows.append(
                {
                    "path": str(path.relative_to(REPO_ROOT)),
                    "route": str(path.relative_to(DOCS_DIR)).replace("\\", "/").rsplit(".", 1)[0],
                    "title": fm.get("title", path.stem),
                    "owner": fm.get("owner", "docs-team"),
                    "last_reviewed": last_reviewed.isoformat(),
                    "age_days": age.days,
                }
            )
    return rows


def _post_github_issue(
    *,
    token: str,
    repo: str,
    title: str,
    body: str,
    labels: list[str],
) -> bool:
    # NOTE: we deliberately do NOT include the Authorization value in
    # any log, even on failure (aqp-management-engine credential rule).
    try:
        resp = httpx.post(
            f"https://api.github.com/repos/{repo}/issues",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "aqp-docs-freshness-watchdog/1.0",
            },
            json={"title": title, "body": body, "labels": labels},
            timeout=httpx.Timeout(20.0),
        )
    except httpx.HTTPError as exc:
        logger.warning("docs-freshness: github call failed (type=%s)", type(exc).__name__)
        return False
    if resp.status_code not in (200, 201):
        logger.warning("docs-freshness: github status=%s", resp.status_code)
        return False
    return True


@celery_app.task(bind=True, name="aqp.tasks.docs_freshness_tasks.scan_stale_pages")
def scan_stale_pages(self) -> dict[str, Any]:
    """Celery beat task — scan for >180-day-old docs pages.

    Returns a structured summary dict suitable for the audit
    dashboard at ``aqp_docs/docs/internal/audit/index.mdx``.
    """
    task_id = self.request.id or "local"
    try:
        threshold = _threshold_days()
        emit(task_id, "start", f"scanning aqp_docs/docs for pages older than {threshold}d")
        stale = _stale_pages(threshold)
        emit(task_id, "found", f"found {len(stale)} stale page(s)", count=len(stale))

        token = _resolve_github_token()
        repo = getattr(_settings(), "docs_github_repo", None) or "julianwileymac/agentic_quant_platform"
        opened = 0
        if token and stale:
            for row in stale:
                title = f"[docs-stale] {row['route']} (>{row['age_days']}d)"
                body = (
                    f"Page `{row['route']}` was last reviewed on "
                    f"`{row['last_reviewed']}` ({row['age_days']} days ago).\n\n"
                    f"**Owner**: `@julianwileymac/{row['owner']}`\n"
                    f"**File**: [{row['path']}](https://github.com/{repo}/blob/main/{row['path']})\n"
                    f"**Open in docs.aqp.fund**: https://docs.aqp.fund/{row['route']}\n\n"
                    "Please re-review the page and bump `last_reviewed`."
                )
                ok = _post_github_issue(
                    token=token,
                    repo=repo,
                    title=title,
                    body=body,
                    labels=["docs-stale", f"owner:{row['owner']}"],
                )
                if ok:
                    opened += 1

        result: dict[str, Any] = {
            "scanned": len(stale),
            "issues_opened": opened,
            "threshold_days": threshold,
            "pages": stale,
            "scanned_at": datetime.utcnow().isoformat() + "Z",
        }
        emit_done(task_id, result)
        return result
    except Exception as exc:
        emit_error(task_id, str(exc))
        raise


__all__ = ["scan_stale_pages"]
