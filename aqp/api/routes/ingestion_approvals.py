"""FastAPI routes for the ingestion-approval workflow (Phase 4)."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/ingestion-approvals", tags=["ingestion-approvals"])


def _resolve_user_id() -> str:
    try:
        from aqp.api.security import current_user_id_dep

        return current_user_id_dep()  # type: ignore[no-any-return]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(401, "unauthenticated") from exc


def _require_step_up() -> Any:
    try:
        from aqp.api.security_stepup import require_step_up

        return require_step_up(max_age_seconds=180)
    except Exception:  # noqa: BLE001
        return None


class ApprovalOut(BaseModel):
    id: str
    tool_id: str
    requested_by_agent_sub: str
    on_behalf_of_user_id: str | None
    args_json: dict[str, Any]
    estimated_cost_tokens: str | None
    status: str
    decided_by_user_id: str | None
    decided_at: datetime | None
    decision_notes: str | None
    expires_at: datetime
    applied_at: datetime | None
    failure_reason: str | None
    created_at: datetime


class DecisionRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=2000)


@router.get("", response_model=list[ApprovalOut])
def list_approvals(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    user_id: str = Depends(_resolve_user_id),
) -> list[ApprovalOut]:
    """List ingestion approvals visible to the calling user."""
    from sqlalchemy import or_

    from aqp.persistence.db import get_session
    from aqp.persistence.models_ingestion_approvals import IngestionApproval

    with get_session() as session:
        q = session.query(IngestionApproval).filter(
            or_(
                IngestionApproval.on_behalf_of_user_id == user_id,
                IngestionApproval.owner_user_id == user_id,
            )
        )
        if status is not None:
            q = q.filter(IngestionApproval.status == status)
        rows = q.order_by(IngestionApproval.created_at.desc()).limit(int(limit)).all()
    return [ApprovalOut.model_validate(row, from_attributes=True) for row in rows]


@router.get("/{approval_id}", response_model=ApprovalOut)
def get_approval(
    approval_id: str,
    user_id: str = Depends(_resolve_user_id),
) -> ApprovalOut:
    """Read one approval by id."""
    from aqp.persistence.db import get_session
    from aqp.persistence.models_ingestion_approvals import IngestionApproval

    with get_session() as session:
        row = session.get(IngestionApproval, approval_id)
        if row is None:
            raise HTTPException(404, "approval not found")
        if row.on_behalf_of_user_id and row.on_behalf_of_user_id != user_id:
            raise HTTPException(403, "approval not addressed to this user")
        return ApprovalOut.model_validate(row, from_attributes=True)


@router.post(
    "/{approval_id}/approve",
    dependencies=[Depends(_require_step_up)],
)
def approve(
    approval_id: str,
    body: DecisionRequest,
    user_id: str = Depends(_resolve_user_id),
) -> dict[str, Any]:
    """Approve a pending ingestion request. Step-up MFA required."""
    from aqp.services.ingestion_approvals import decide_approval

    result = decide_approval(
        approval_id=approval_id,
        approve=True,
        decided_by_user_id=user_id,
        notes=body.notes,
    )
    if not result.get("ok"):
        raise HTTPException(400, result.get("error") or "decide failed")
    return result


@router.post(
    "/{approval_id}/reject",
    dependencies=[Depends(_require_step_up)],
)
def reject(
    approval_id: str,
    body: DecisionRequest,
    user_id: str = Depends(_resolve_user_id),
) -> dict[str, Any]:
    """Reject a pending ingestion request. Step-up MFA required."""
    from aqp.services.ingestion_approvals import decide_approval

    result = decide_approval(
        approval_id=approval_id,
        approve=False,
        decided_by_user_id=user_id,
        notes=body.notes,
    )
    if not result.get("ok"):
        raise HTTPException(400, result.get("error") or "decide failed")
    return result


__all__ = ["router"]
