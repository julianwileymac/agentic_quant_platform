"""``/workloads`` — embedded-mode kill-switch fan-out for the WorkloadRuntime.

Phase 2b of the AQP control-plane maturation. Mirrors the sidecar
``aqp_control_plane/src/aqp_cp/api/routers/workloads.py`` so that the
frontend ``KillSwitch`` UI component (which fans out to nine halt
endpoints in parallel — see
``frontend/src/components/common/KillSwitch.tsx``) gets the same
``POST /workloads/halt`` surface whether the operator is running AQP
in ``embedded`` mode (single monolith, default for local dev and most
deployments) or ``sidecar`` mode (separate ``aqp_cp`` process).

Per AGENTS rule 45, every runtime workload op (start / stop / scale /
restart / exec / logs / apply_config / rotate_secret) goes through
:class:`aqp_platform_core.runtime.workload.WorkloadRuntime`. The
runtime exposes :meth:`halt_all` that signals every in-flight run to
abort via the process-wide
:class:`aqp_platform_core.runtime.workload._HaltRegistry`. This route
is the embedded HTTP surface for that fan-out.

Authorization: ``workloads:halt`` scope. Granted to every role from
``aqp-operator`` upward (see ``docs/scopes.md``).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, Header, Query, Request
from pydantic import BaseModel, Field

from aqp.api.security import require_dpop_token, require_scope, secure_router
from aqp.auth import CurrentUser
from aqp.auth.scopes import AQPScope
from aqp_platform_core.runtime.workload import (
    WorkloadRuntime,
    get_halt_registry,
)

logger = logging.getLogger(__name__)

router = secure_router(
    prefix="/workloads",
    tags=["workloads"],
    default_scope=AQPScope.READ_INFRASTRUCTURE,
)


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
    user_id: str | None = None


def _resolve_provider_alias() -> str:
    """Return the active provider alias for the embedded WorkloadRuntime.

    Reads the canonical settings field; falls back to ``"docker_compose"``
    for local-first development. The runtime accepts any registered
    alias — the alias is only used to build the audit row's ``provider``
    field, not to dispatch a real provider call (the halt fan-out is a
    process-wide registry op).
    """
    try:
        from aqp.config import settings

        alias = (
            getattr(settings, "infrastructure_provider", None)
            or getattr(settings, "management_provider", None)
            or getattr(settings, "control_plane_provider", None)
            or "docker_compose"
        )
        return str(alias)
    except Exception:  # noqa: BLE001
        return "docker_compose"


@router.post(
    "/halt",
    summary="Halt every in-flight WorkloadRuntime run.",
    description=(
        "Kill-switch fan-out for runtime workload operations (AGENTS rule 45). "
        "Signals every in-flight `WorkloadRun` on this process to abort. "
        "Each affected run writes its own status=HALTED audit row when it "
        "observes the signal. Idempotent. Required scope: `workloads:halt`."
    ),
)
def halt_workloads(
    request: Request,
    body: HaltRequest | None = None,
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    user: CurrentUser = Depends(require_scope(AQPScope.WORKLOADS_HALT)),
    _dpop: CurrentUser = Depends(require_dpop_token()),
) -> HaltResponse:
    reason = (body.reason if body else None) or "kill-switch"
    alias = _resolve_provider_alias()

    runtime = WorkloadRuntime(provider_alias=alias)
    halted_count = runtime.halt_all(reason=reason)

    triggered_at = datetime.now(timezone.utc)

    user_id = getattr(user, "internal_id", None) or getattr(user, "auth_subject", None)
    logger.warning(
        "workloads_halt_requested user_id=%s halted_count=%d reason=%r request_id=%s",
        user_id,
        halted_count,
        reason,
        x_request_id,
    )

    # Best-effort audit row via the existing security audit ledger
    # (separate from the WorkloadRun rows the registry writes per
    # affected run). This row records the halt fan-out trigger itself.
    try:
        from aqp.auth.audit import emit_audit_event

        emit_audit_event(
            "workloads_halt",
            user_id=user_id,
            event_category="kill_switch",
            severity="warning",
            source="workloads_halt_route",
            request=request,
            details={
                "halted_count": halted_count,
                "reason": reason,
                "provider_alias": alias,
            },
        )
    except Exception:  # noqa: BLE001
        pass

    return HaltResponse(
        halted_count=halted_count,
        reason=reason,
        triggered_at=triggered_at,
        user_id=str(user_id) if user_id else None,
    )


@router.get(
    "/halt/status",
    summary="Inspect the current halt-registry state.",
    description=(
        "Returns the count of currently in-flight WorkloadRun rows and "
        "whether the global halt flag is set. Used by the KillSwitch UI "
        "to render the post-halt confirmation screen and by smoke tests "
        "to verify the halt fan-out worked. Required scope: "
        "`read:infrastructure`."
    ),
)
def halt_status() -> dict[str, Any]:
    registry = get_halt_registry()
    inflight_count = len(registry._inflight)  # type: ignore[attr-defined]
    global_reason = registry._global_halt_reason  # type: ignore[attr-defined]
    return {
        "inflight_count": inflight_count,
        "global_halt_active": global_reason is not None,
        "global_halt_reason": global_reason,
    }


@router.post(
    "/halt/clear",
    summary="Clear the global halt flag (super-admin only).",
    description=(
        "Resets the global halt flag so subsequent WorkloadRuntime calls "
        "proceed normally. Does NOT resume already-halted runs (those are "
        "terminal). Use after an operator confirms the incident is over "
        "and the platform should accept new work. Required scope: "
        "`platform:admin`."
    ),
)
def clear_halt(
    confirm: bool = Query(default=False, description="Must be ``true`` to take effect."),
    user: CurrentUser = Depends(require_scope(AQPScope.PLATFORM_ADMIN)),
) -> dict[str, Any]:
    if not confirm:
        return {
            "cleared": False,
            "note": "Pass ?confirm=true to clear the global halt flag.",
        }
    registry = get_halt_registry()
    registry.clear_global()
    user_id = getattr(user, "internal_id", None) or getattr(user, "auth_subject", None)
    logger.warning("workloads_halt_cleared user_id=%s", user_id)
    return {"cleared": True, "user_id": str(user_id) if user_id else None}


__all__ = ["router"]
