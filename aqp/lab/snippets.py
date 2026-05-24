"""Snippet save / promote / version flow.

Backs the ``lab_snippets`` table and the EDA "Promote to node"
context menu. Snippets carry an always-on AST safety check (the
same one used by the EDA kernel — see
:func:`aqp.lab.eda.kernel._ast_safety_check`). Promoted snippets
register as virtual NodeTypes in the palette so the user can drag
them into a Testing graph; the Phase 5 Tier-1 (Pyodide) / Tier-2
(gVisor-Docker) snippet runners ship with the plan §16 timing.

This module is intentionally framework-light — it never instantiates
a Pyodide / Docker runner directly. It just persists the snippet
+ records the run history, and exposes :func:`describe_snippet` for
the registry / runtime to look up the source at execution time.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from aqp.lab.eda.kernel import CellSafetyError, _ast_safety_check

logger = logging.getLogger(__name__)


# Snippet languages the AST safety guard supports. SQL snippets are
# allowed but skip the AST guard; they go through the DuckDB / QuestDB
# tools which have their own policy checks.
SNIPPET_LANGUAGES: tuple[str, ...] = ("python", "sql")


@dataclass(frozen=True)
class SnippetDescriptor:
    """Static description of a snippet without binding to an ORM row."""

    id: str
    name: str
    language: str
    source: str
    content_hash: str
    ast_safe: bool
    version: int
    promoted: bool
    manifest: dict[str, Any]


def compute_snippet_hash(source: str, language: str) -> str:
    """Stable SHA256 of (language, normalised source)."""
    norm = (language.lower().strip(), (source or "").rstrip())
    canonical = "\n".join([*norm[0], norm[1]])
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def safety_check(source: str, language: str) -> bool:
    """Return ``True`` when the snippet passes the AST guard.

    Never raises. The Tier-1 / Tier-2 runners re-run the guard
    before exec; this is the upfront feedback for the editor.
    """
    language = language.lower().strip()
    if language != "python":
        return True
    try:
        _ast_safety_check(source or "")
        return True
    except CellSafetyError as exc:
        logger.debug("snippet safety check rejected: %s", exc)
        return False
    except Exception:  # noqa: BLE001
        return False


def save_snippet(
    *,
    workspace_id: str,
    name: str,
    source: str,
    language: str = "python",
    lab_id: str | None = None,
    owner_user_id: str | None = None,
    manifest: dict[str, Any] | None = None,
    parent_snippet_id: str | None = None,
) -> str | None:
    """Persist a new snippet row; returns the row id on success.

    The version starts at 1 and bumps on every successful save under
    the same (workspace_id, name); the unique constraint in migration
    0057 enforces (workspace_id, name, version) uniqueness.
    """
    if language not in SNIPPET_LANGUAGES:
        raise ValueError(f"unknown snippet language {language!r}")
    safe = safety_check(source, language)
    content_hash = compute_snippet_hash(source, language)
    manifest = dict(manifest or {})
    try:
        from sqlalchemy import select

        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_lab import LabSnippet

        with SessionLocal() as session:
            # Find the current max version for (workspace, name).
            latest = (
                session.query(LabSnippet)
                .filter(
                    LabSnippet.workspace_id == workspace_id,
                    LabSnippet.name == name,
                )
                .order_by(LabSnippet.version.desc())
                .first()
            )
            next_version = (latest.version if latest else 0) + 1
            row = LabSnippet(
                id=str(uuid4()),
                workspace_id=workspace_id,
                lab_id=lab_id,
                owner_user_id=owner_user_id,
                name=name,
                language=language,
                source=source or "",
                manifest=manifest,
                content_hash=content_hash,
                ast_safe=safe,
                version=next_version,
                parent_snippet_id=parent_snippet_id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(row)
            session.commit()
            return row.id
    except Exception:  # noqa: BLE001 - never block the EDA promote flow
        logger.warning("save_snippet failed", exc_info=True)
        return None


def describe_snippet(snippet_id: str) -> SnippetDescriptor | None:
    """Return a serialisable descriptor for an existing snippet."""
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_lab import LabSnippet

        with SessionLocal() as session:
            row = session.get(LabSnippet, snippet_id)
            if row is None:
                return None
            return SnippetDescriptor(
                id=row.id,
                name=row.name,
                language=row.language,
                source=row.source,
                content_hash=row.content_hash,
                ast_safe=bool(row.ast_safe),
                version=int(row.version),
                promoted=bool(row.promoted),
                manifest=dict(row.manifest or {}),
            )
    except Exception:  # noqa: BLE001
        return None


def promote_snippet(snippet_id: str) -> bool:
    """Mark a snippet as ``promoted=True`` so it appears in the palette."""
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_lab import LabSnippet

        with SessionLocal() as session:
            row = session.get(LabSnippet, snippet_id)
            if row is None:
                return False
            row.promoted = True
            row.updated_at = datetime.utcnow()
            session.commit()
            return True
    except Exception:  # noqa: BLE001
        return False


__all__ = [
    "SNIPPET_LANGUAGES",
    "SnippetDescriptor",
    "compute_snippet_hash",
    "describe_snippet",
    "promote_snippet",
    "safety_check",
    "save_snippet",
]
