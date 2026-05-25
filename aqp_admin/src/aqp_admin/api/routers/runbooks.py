"""``/admin/runbooks`` — TipTap runbook editor persistence.

In-memory store for now (the persistent layer lands when the admin
package adopts SQLAlchemy in a follow-up). Audit-first writes per
``aqp_admin/AGENTS.md``.
"""
from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from aqp_admin.deps.audit import AuditContext, audit_context_dep
from aqp_admin.deps.identity import AdminUser, require_admin_scope

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/runbooks", tags=["runbooks"])

_RUNBOOKS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


class RunbookBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    doc: dict[str, Any] = Field(
        ...,
        description="TipTap document JSON (`type: 'doc'`).",
    )
    tags: list[str] = Field(default_factory=list)


class RunbookSummary(BaseModel):
    id: str
    title: str
    updated_at: datetime
    tags: list[str]


@router.get("", summary="List runbooks (titles + tags only).")
async def list_runbooks(
    user: AdminUser = Depends(require_admin_scope("read:audit")),
) -> dict[str, list[RunbookSummary]]:
    with _LOCK:
        rows = [
            RunbookSummary(
                id=rb["id"],
                title=rb["title"],
                updated_at=rb["updated_at"],
                tags=list(rb.get("tags", [])),
            )
            for rb in _RUNBOOKS.values()
        ]
    return {"runbooks": rows}


@router.post(
    "",
    summary="Create or update a runbook (audit-first).",
)
async def upsert_runbook(
    body: RunbookBody,
    user: AdminUser = Depends(require_admin_scope("manage:tenants")),
    audit: AuditContext = Depends(audit_context_dep("admin.runbooks.upsert")),
) -> dict[str, Any]:
    audit.target = body.title
    audit.start(payload={"title": body.title, "tags": body.tags})
    runbook_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    record = {
        "id": runbook_id,
        "title": body.title,
        "doc": body.doc,
        "tags": list(body.tags),
        "updated_at": now,
        "author_sub": user.sub,
    }
    with _LOCK:
        _RUNBOOKS[runbook_id] = record
    audit.succeed({"runbook_id": runbook_id})
    return {"runbook": _serialise(record)}


@router.get(
    "/{runbook_id}",
    summary="Read a single runbook document.",
)
async def get_runbook(
    runbook_id: str,
    user: AdminUser = Depends(require_admin_scope("read:audit")),
) -> dict[str, Any]:
    with _LOCK:
        record = _RUNBOOKS.get(runbook_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "runbook_not_found", "runbook_id": runbook_id},
        )
    return {"runbook": _serialise(record)}


def _serialise(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record["id"],
        "title": record["title"],
        "doc": record["doc"],
        "tags": list(record.get("tags", [])),
        "updated_at": record["updated_at"].isoformat()
        if isinstance(record["updated_at"], datetime)
        else record["updated_at"],
        "author_sub": record.get("author_sub"),
    }


__all__ = ["router"]
