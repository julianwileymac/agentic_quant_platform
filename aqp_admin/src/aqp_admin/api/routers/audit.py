"""``/admin/audit`` — recent admin-side audit rows for the UI history pane.

Reads from the JSONL audit file when ``AQP_ADMIN_AUDIT_SINK=jsonl``;
the HTTP-sink mode delegates persistence to the monolith and the
monolith owns the query API (this router returns 501 in that mode
with a helpful error envelope).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status

from aqp_admin.deps.identity import AdminUser, require_admin_scope
from aqp_admin.integrations import AdminBrokerError, get_brokers
from aqp_admin.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/audit", tags=["audit"])


def _bearer_from_header(header_value: str | None) -> str | None:
    if not header_value or not header_value.lower().startswith("bearer "):
        return None
    return header_value.split(None, 1)[1].strip()


@router.get(
    "/runs",
    summary="Tail recent admin audit rows (JSONL sink only).",
)
async def list_runs(
    limit: int = 100,
    user: AdminUser = Depends(require_admin_scope("read:audit")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    settings = get_settings()
    if settings.audit_sink != "jsonl":
        try:
            return await get_brokers().monolith.list_admin_audit_runs(
                limit=limit,
                bearer_passthrough=_bearer_from_header(authorization),
            )
        except AdminBrokerError as exc:
            raise HTTPException(
                status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
                detail={"error": exc.code, "error_description": str(exc)},
            ) from exc
    path = Path(settings.audit_jsonl_path)
    if not path.exists():
        return {"runs": [], "path": str(path), "available": False}
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "audit_read_failed", "error_description": str(exc)},
        ) from exc
    rows.reverse()
    return {
        "runs": rows[: max(1, min(limit, 1000))],
        "path": str(path),
        "available": True,
    }


__all__ = ["router"]
