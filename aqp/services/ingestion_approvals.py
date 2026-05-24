"""Service layer for ingestion approval workflow (Phase 4, plan section 8).

When an autonomous agent invokes a mutating ``data.ingest.*`` or
``data.transform.*`` MCP tool, the tool calls
:func:`request_approval` instead of executing the side effect.
The on-behalf-of user approves or rejects through
``/ingestion-approvals/{id}/{approve|reject}`` within the 24h TTL.
On approval, the Celery task in
:mod:`aqp.tasks.ingestion_approval_tasks` materializes the original
side effect with the saved arguments.

Returns from :func:`request_approval` are deliberately uniform —
``{"status": "pending_approval", "approval_id": "<uuid>", ...}`` —
so MCP tools can short-circuit cleanly when the actor is an
agent.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


_DEFAULT_TTL_HOURS = 24


def request_approval(
    *,
    tool_id: str,
    args: dict[str, Any],
    requested_by_agent_sub: str,
    on_behalf_of_user_id: str | None,
    workspace_id: str | None = None,
    estimated_cost_tokens: int | None = None,
    ttl_hours: int = _DEFAULT_TTL_HOURS,
) -> dict[str, Any]:
    """Persist a pending approval and return the canonical response shape."""
    from aqp.persistence.db import get_session
    from aqp.persistence.models_ingestion_approvals import (
        STATUS_PENDING,
        IngestionApproval,
    )

    expires_at = datetime.utcnow() + timedelta(hours=int(ttl_hours))
    with get_session() as session:
        row = IngestionApproval(
            owner_user_id=on_behalf_of_user_id,
            workspace_id=workspace_id,
            tool_id=tool_id,
            args_json=args,
            requested_by_agent_sub=requested_by_agent_sub,
            on_behalf_of_user_id=on_behalf_of_user_id,
            estimated_cost_tokens=(
                str(estimated_cost_tokens) if estimated_cost_tokens else None
            ),
            status=STATUS_PENDING,
            expires_at=expires_at,
        )
        session.add(row)
        session.commit()
        approval_id = row.id

    # Best-effort audit emit.
    try:
        from aqp.auth.audit import emit_audit_event

        emit_audit_event(
            event_type="ingestion_approval.requested",
            event_category="ingest",
            user_id=on_behalf_of_user_id,
            details={
                "approval_id": approval_id,
                "tool_id": tool_id,
                "agent_subject": requested_by_agent_sub,
                "estimated_cost_tokens": estimated_cost_tokens,
                "args_redacted": _redact(args),
            },
        )
    except Exception:  # noqa: BLE001
        logger.debug("audit emit failed for approval %s", approval_id, exc_info=True)

    return {
        "status": "pending_approval",
        "approval_id": approval_id,
        "tool_id": tool_id,
        "expires_at": expires_at.isoformat(),
        "agent_subject": requested_by_agent_sub,
        "on_behalf_of_user_id": on_behalf_of_user_id,
    }


def decide_approval(
    *,
    approval_id: str,
    approve: bool,
    decided_by_user_id: str,
    notes: str | None = None,
) -> dict[str, Any]:
    """Approve or reject a pending request."""
    from aqp.persistence.db import get_session
    from aqp.persistence.models_ingestion_approvals import (
        STATUS_APPROVED,
        STATUS_PENDING,
        STATUS_REJECTED,
        IngestionApproval,
    )

    with get_session() as session:
        row = session.get(IngestionApproval, approval_id)
        if row is None:
            return {"ok": False, "error": "approval not found"}
        if row.status != STATUS_PENDING:
            return {
                "ok": False,
                "error": f"approval already in terminal state {row.status!r}",
            }
        if row.expires_at and row.expires_at < datetime.utcnow():
            return {"ok": False, "error": "approval expired"}
        if row.on_behalf_of_user_id and decided_by_user_id != row.on_behalf_of_user_id:
            return {"ok": False, "error": "only the on-behalf-of user can decide"}
        row.status = STATUS_APPROVED if approve else STATUS_REJECTED
        row.decided_by_user_id = decided_by_user_id
        row.decided_at = datetime.utcnow()
        row.decision_notes = notes
        session.commit()
        out = {
            "ok": True,
            "approval_id": approval_id,
            "status": row.status,
            "tool_id": row.tool_id,
        }

    try:
        from aqp.auth.audit import emit_audit_event

        emit_audit_event(
            event_type=(
                "ingestion_approval.approved"
                if approve
                else "ingestion_approval.rejected"
            ),
            event_category="ingest",
            user_id=decided_by_user_id,
            details={
                "approval_id": approval_id,
                "tool_id": out["tool_id"],
                "decision_notes": notes,
            },
        )
    except Exception:  # noqa: BLE001
        logger.debug("audit emit failed for approval %s", approval_id, exc_info=True)

    if approve:
        try:
            from aqp.tasks.ingestion_approval_tasks import apply_approval

            apply_approval.delay(approval_id)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            logger.debug(
                "apply_approval task dispatch failed for %s",
                approval_id,
                exc_info=True,
            )

    return out


def _redact(args: dict[str, Any]) -> dict[str, Any]:
    """Strip likely secrets from an args payload for audit logging."""
    redacted_keys = {"api_key", "api_secret", "password", "token", "secret"}
    out: dict[str, Any] = {}
    for key, value in (args or {}).items():
        if key.lower() in redacted_keys:
            out[key] = "<redacted>"
        elif isinstance(value, dict):
            out[key] = _redact(value)
        else:
            out[key] = value
    return out


__all__ = ["decide_approval", "request_approval"]
