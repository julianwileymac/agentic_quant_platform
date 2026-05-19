"""``/manage/workloads`` — kill-switch fan-out for the WorkloadRuntime.

Phase 2b of the AQP control-plane maturation. Implements the missing
``POST /workloads/halt`` endpoint that the frontend ``KillSwitch`` UI
component already lists in its fan-out catalogue.

Per AGENTS rule 45, every runtime workload op (start / stop / scale /
restart / exec / logs / apply_config / rotate_secret) goes through the
:class:`aqp_platform_core.runtime.workload.WorkloadRuntime`. The
runtime exposes :meth:`halt_all` that signals every in-flight run to
abort via the process-wide
:class:`aqp_platform_core.runtime.workload._HaltRegistry`. This route
is the HTTP surface for that fan-out.

Authorization: ``workloads:halt`` scope. Granted to every role from
``aqp-operator`` upward (the kill-switch must be reachable from every
operator console; super-admins inherit it via the lattice).

Audit trail: a ``WorkloadRun`` row is written via the active audit
sink for the halt event itself (action=``HALT``), with the count of
runs cancelled in the ``result`` payload. The runtime's per-run finish
hook also writes ``status=HALTED`` rows for each run that was
interrupted, so the audit ledger has both the fan-out trigger and the
per-run halt evidence.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field

from aqp_cp.auth.deps import AuthenticatedUser, require_scope
from aqp_cp.models import ResponseEnvelope
from aqp_cp.services.lifecycle import get_active_provider
from aqp_platform_core.runtime.workload import (
    WorkloadRuntime,
    get_halt_registry,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["workloads"])


class HaltRequest(BaseModel):
    """Operator-supplied reason string for the halt event."""

    reason: str = Field(
        default="kill-switch",
        description=(
            "Free-form reason the operator is invoking the kill switch. "
            "Persisted in the WorkloadRun audit row so post-mortem reviews "
            "can correlate the halt with the operator's intent."
        ),
        max_length=512,
    )


class HaltResponse(BaseModel):
    """Result payload returned to the frontend KillSwitch dialog."""

    halted_count: int = Field(
        ...,
        description=(
            "Number of in-flight WorkloadRun rows that received the halt "
            "signal at the moment the kill switch fired. Each affected run "
            "writes its own status=HALTED row when it observes the signal."
        ),
    )
    reason: str
    triggered_at: datetime
    user_id: str


@router.post(
    "/workloads/halt",
    summary="Halt every in-flight WorkloadRuntime run.",
    description=(
        "Kill-switch fan-out for runtime workload operations. Signals every "
        "in-flight `WorkloadRun` on this control-plane process to abort. "
        "Each affected run writes its own status=HALTED audit row when it "
        "observes the signal (per-runtime cooperative cancellation). "
        "Idempotent — calling the endpoint repeatedly while the halt flag "
        "is set is a no-op until the registry is cleared. "
        "Required scope: `workloads:halt`."
    ),
    response_model=ResponseEnvelope[HaltResponse],
)
async def halt_workloads(
    request: Request,
    body: HaltRequest | None = None,
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    user: AuthenticatedUser = Depends(require_scope("workloads:halt")),
) -> ResponseEnvelope[HaltResponse]:
    reason = (body.reason if body else None) or "kill-switch"

    # Halt fan-out is a registry-level operation; we don't bind it to a
    # specific provider alias because the registry is process-wide. We
    # build a transient WorkloadRuntime only so the halt() call goes
    # through the canonical surface and is audit-logged consistently.
    provider = get_active_provider()
    provider_alias = getattr(provider, "alias", None) or getattr(
        provider, "provider_kind", "default"
    )
    runtime = WorkloadRuntime(provider_alias=provider_alias)
    halted_count = runtime.halt_all(reason=reason)

    triggered_at = datetime.now(timezone.utc)

    logger.warning(
        "workloads_halt_requested user_id=%s halted_count=%d reason=%r request_id=%s",
        user.user_id,
        halted_count,
        reason,
        x_request_id,
    )

    return ResponseEnvelope(
        status="ok",
        data=HaltResponse(
            halted_count=halted_count,
            reason=reason,
            triggered_at=triggered_at,
            user_id=user.user_id,
        ),
    )


@router.get(
    "/workloads/halt/status",
    summary="Inspect the current halt-registry state.",
    description=(
        "Returns the count of currently in-flight WorkloadRun rows on this "
        "process and whether the global halt flag is currently set. "
        "Used by the KillSwitch UI to render the post-halt confirmation "
        "screen and by smoke tests to verify the halt fan-out worked. "
        "Required scope: `read:infrastructure`."
    ),
    response_model=ResponseEnvelope[dict[str, Any]],
)
async def halt_status(
    request: Request,
    user: AuthenticatedUser = Depends(require_scope("read:infrastructure")),
) -> ResponseEnvelope[dict[str, Any]]:
    registry = get_halt_registry()
    inflight_count = len(registry._inflight)  # type: ignore[attr-defined]
    global_reason = registry._global_halt_reason  # type: ignore[attr-defined]
    return ResponseEnvelope(
        status="ok",
        data={
            "inflight_count": inflight_count,
            "global_halt_active": global_reason is not None,
            "global_halt_reason": global_reason,
        },
    )


__all__ = ["router"]
