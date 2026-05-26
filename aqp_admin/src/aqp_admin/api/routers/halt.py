"""``/admin/halt`` — kill-switch fan-out from the admin UI topbar.

The frontend ``KillSwitch`` calls a single brokered endpoint instead
of hitting each halt URL directly. The broker fans out to:

- ``POST /manage/workloads/halt`` (control plane)
- ``POST /manage/terraform/halt`` (control plane)
- ``POST /agents/halt``, ``/paper/stop-all``, ``/bots/halt-all``,
  ``/rl/halt-all``, ``/quant-agents/halt``, ``/workflows/halt``
  (monolith)

Audit-first per ``aqp_admin/AGENTS.md``: the row is written BEFORE
the fan-out. Partial failures appear in the response ``failures``
array — the audit row's ``status`` reflects whether any sub-call
failed.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from aqp_admin.deps.audit import AuditContext, audit_context_dep
from aqp_admin.deps.identity import AdminUser
from aqp_admin.deps.stepup import require_admin_step_up
from aqp_admin.integrations import get_brokers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/halt", tags=["halt"])


class HaltAllBody(BaseModel):
    reason: str = Field(default="kill-switch", max_length=512)


class HaltAllResponse(BaseModel):
    triggered_at: datetime
    user_id: str
    reason: str
    halted: list[dict[str, Any]]
    failures: list[dict[str, Any]]


def _bearer_from_header(header_value: str | None) -> str | None:
    if not header_value or not header_value.lower().startswith("bearer "):
        return None
    return header_value.split(None, 1)[1].strip()


@router.post(
    "/all",
    summary="Engage the kill-switch — fan out to every halt endpoint (audit-first).",
    response_model=HaltAllResponse,
)
async def halt_all(
    body: HaltAllBody | None = None,
    user: AdminUser = Depends(
        require_admin_step_up("workloads:halt", max_age_seconds=180),
    ),
    audit: AuditContext = Depends(audit_context_dep("admin.halt.all")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> HaltAllResponse:
    reason = (body.reason if body else None) or "kill-switch"
    audit.target = "kill-switch"
    audit.start(payload={"reason": reason})
    bearer = _bearer_from_header(authorization)
    brokers = get_brokers()
    result = await brokers.halt.halt_all(reason, bearer_passthrough=bearer)
    response = HaltAllResponse(
        triggered_at=datetime.now(timezone.utc),
        user_id=user.sub,
        reason=reason,
        halted=result["halted"],
        failures=result["failures"],
    )
    if result["failures"]:
        audit.fail(f"partial kill-switch ({len(result['failures'])} failure(s))")
    else:
        audit.succeed({"halted_count": len(result["halted"])})
    return response


__all__ = ["router"]
