"""Celery tasks that materialize approved ingestion-tool side effects."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


def apply_approval_sync(approval_id: str) -> dict[str, Any]:
    """Synchronously apply an approved ingestion-tool invocation.

    Separated from the Celery wrapper so unit tests can drive it
    without a broker.
    """
    from aqp.persistence.db import get_session
    from aqp.persistence.models_ingestion_approvals import (
        STATUS_APPLIED,
        STATUS_APPROVED,
        STATUS_FAILED,
        IngestionApproval,
    )

    with get_session() as session:
        row = session.get(IngestionApproval, approval_id)
        if row is None:
            return {"ok": False, "error": "approval not found"}
        if row.status != STATUS_APPROVED:
            return {
                "ok": False,
                "error": f"approval is {row.status!r}, expected approved",
            }
        tool_id = row.tool_id
        args = dict(row.args_json or {})
    try:
        from aqp.data.mcp.registry import get_data_mcp_tool

        tool = get_data_mcp_tool(tool_id)
        # Bypass the agent-actor guard by minting a service-actor
        # context — the human already approved.
        from aqp.data.mcp.base import MCPToolContext

        ctx = MCPToolContext(
            actor=row.decided_by_user_id,
            actor_kind="service",
            workspace_id=row.workspace_id,
            granted_scopes=("data:read", "data:write"),
            extras={"approval_id": approval_id},
        )
        result = tool.invoke(ctx=ctx, **args)
        ok = bool(getattr(result, "ok", False))
    except Exception as exc:  # noqa: BLE001
        ok = False
        result = None
        failure_reason: str | None = str(exc)
    else:
        failure_reason = None if ok else (getattr(result, "error", None) or "")

    with get_session() as session:
        row = session.get(IngestionApproval, approval_id)
        if row is not None:
            row.status = STATUS_APPLIED if ok else STATUS_FAILED
            row.applied_at = datetime.utcnow()
            if failure_reason:
                row.failure_reason = failure_reason
            session.commit()

    return {"ok": ok, "approval_id": approval_id, "failure_reason": failure_reason}


try:
    from aqp.tasks.celery_app import celery_app

    @celery_app.task(bind=True, name="aqp.tasks.ingestion_approval_tasks.apply_approval")
    def apply_approval(self, approval_id: str) -> dict[str, Any]:  # noqa: ARG001
        return apply_approval_sync(approval_id)
except Exception:  # noqa: BLE001
    # Celery wiring is optional in unit-test environments. The
    # `apply_approval_sync` function is still importable.
    def apply_approval(approval_id: str) -> dict[str, Any]:  # type: ignore[no-redef]
        return apply_approval_sync(approval_id)


__all__ = ["apply_approval", "apply_approval_sync"]
