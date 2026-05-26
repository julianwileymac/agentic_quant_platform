"""``/_internal/audit/*`` — sink endpoints for the CP audit bridge.

When the CP runs out-of-process (``AQP_TERRAFORM_USE_CONTROL_PLANE=true``)
its in-process audit sinks can't reach the monolith's Postgres directly.
The CP-side
:class:`aqp_cp.services.http_audit_sink.HttpAuditSink` and
:class:`aqp_cp.terraform.audit_sink.HttpTerraformAuditSink` POST every
ledger row to one of these endpoints; the route persists into the
matching ORM table so the operator UI keeps reading from a single
source of truth.

Two endpoints today:

- ``POST /_internal/audit/workload-runs``   — for ``WorkloadRun`` rows.
- ``POST /_internal/audit/terraform-runs``  — for ``TerraformRun`` rows.

The routes are intentionally outside the normal ``/auth/...`` prefix,
deliberately NOT covered by the global ``secure_router`` (which demands
a Bearer JWT), and are public to the FastAPI surface — but every
request MUST carry a valid M2M Bearer token whose audience matches
:attr:`Settings.auth_m2m_audience`. The CP's
:class:`M2MTokenBroker` mints the token via the Auth0 / Entra client
credentials flow at boot.

Per AGENTS rule 27 the validation goes through ``aqp.auth.providers``
(no direct vendor SDK calls).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/_internal/audit", tags=["internal-audit"])


# ---------------------------------------------------------------------------
# M2M token verification (mirrors aqp/api/routes/auth0_sync.py::require_m2m_token)
# ---------------------------------------------------------------------------


def _require_m2m_bearer(authorization: str | None) -> dict[str, Any]:
    """Validate the Bearer token using the active OIDC provider.

    Returns the verified claims dict so the route handler can audit
    which CP instance posted the row.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(None, 1)[1].strip()

    from aqp.auth.oidc import (
        InvalidTokenError,
        OIDCConfig,
        get_oidc_config,
        validate_jwt,
    )

    cfg = get_oidc_config()
    if cfg is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC is not configured",
        )

    try:
        from aqp.config import settings

        m2m_audience = (
            str(getattr(settings, "auth_m2m_audience", "") or "").strip()
            or cfg.audience
        )
    except Exception:
        m2m_audience = cfg.audience

    m2m_cfg = OIDCConfig(
        issuer=cfg.issuer,
        audience=m2m_audience,
        client_id=cfg.client_id,
        jwks_ttl_seconds=cfg.jwks_ttl_seconds,
        leeway_seconds=cfg.leeway_seconds,
    )

    try:
        return validate_jwt(token, config=m2m_cfg)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.warning("M2M validation failed in _internal_audit: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token validation failed",
        ) from exc


# ---------------------------------------------------------------------------
# Wire schemas — match the CP-side audit-sink payloads
# ---------------------------------------------------------------------------


class TerraformRunAuditPayload(BaseModel):
    """Wire schema for /terraform-runs ingest.

    ``phase`` is either ``start`` (queued row, no result yet) or
    ``finish`` (final TerraformRunResult.model_dump()).
    """

    model_config = {"extra": "allow"}

    phase: str = Field(..., description="'start' | 'finish'")
    run_id: str
    run_kind: str | None = None
    stack_name: str | None = None
    workspace_id: str | None = None
    state_backend: str | None = None
    spec_hash: str | None = None
    status: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: float | None = None
    plan_summary: dict[str, Any] | None = None
    log_excerpt: str | None = None
    artifact_uri: str | None = None
    error: str | None = None
    halt_reason: str | None = None
    initiated_by_user_id: str | None = None
    approver_user_id: str | None = None
    experiment_id: str | None = None
    test_id: str | None = None
    user_id: str | None = Field(default=None, description="Alias for initiated_by_user_id on start phase.")
    queued_at: datetime | None = None
    request_id: str | None = None
    org_id: str | None = None


class WorkloadRunAuditPayload(BaseModel):
    """Wire schema for /workload-runs ingest.

    Mirror of :class:`aqp_platform_core.models.workloads.WorkloadRun`
    with the ``phase`` discriminator added by the CP HTTP audit sink.
    """

    model_config = {"extra": "allow"}

    phase: str
    run_id: str | None = None


# ---------------------------------------------------------------------------
# /terraform-runs ingest
# ---------------------------------------------------------------------------


_TERRAFORM_KIND_TO_DB: dict[str, str] = {
    "plan": "plan",
    "apply": "apply",
    "destroy": "destroy",
    "refresh": "refresh",
    "import": "import",
    "state_pull": "state_pull",
    "validate": "validate",
    "unlock": "unlock",
}

_TERRAFORM_STATUS_TO_DB: dict[str, str] = {
    "pending": "queued",
    "running": "running",
    "succeeded": "completed",
    "failed": "errored",
    "halted": "cancelled",
    "rejected": "cancelled",
}


@router.post("/terraform-runs", include_in_schema=False)
def ingest_terraform_run(
    body: TerraformRunAuditPayload,
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """Persist a ``terraform_runs`` row dispatched by the CP audit sink.

    Idempotent on (``run_id``, ``phase``). Re-delivery of the same
    phase updates the row in-place; the runtime contract uses the
    first-write-wins semantic for the started_at column so retries
    don't reset the queue timestamp.
    """
    claims = _require_m2m_bearer(authorization)
    actor = claims.get("sub") or claims.get("client_id") or "cp"

    try:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_terraform import (
            TerraformRun,
            TerraformWorkspace,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("terraform-runs ingest: ORM unavailable (%s); dropping", exc)
        return {"ok": True, "persisted": False, "reason": "orm unavailable"}

    with get_session() as session:
        existing = (
            session.query(TerraformRun)
            .filter(TerraformRun.id == body.run_id)
            .one_or_none()
        )
        ws_id = body.workspace_id
        ws_row = None
        if ws_id:
            ws_row = (
                session.query(TerraformWorkspace)
                .filter(TerraformWorkspace.id == ws_id)
                .one_or_none()
            )
            if ws_row is None:
                ws_row = (
                    session.query(TerraformWorkspace)
                    .filter(TerraformWorkspace.slug == ws_id)
                    .one_or_none()
                )

        if existing is None:
            if ws_row is None:
                logger.warning(
                    "terraform-runs ingest: no workspace match for %s; dropping row",
                    ws_id,
                )
                return {"ok": True, "persisted": False, "reason": "workspace not found"}
            existing = TerraformRun(
                id=body.run_id,
                terraform_workspace_id=ws_row.id,
                spec_version_id=None,
                run_kind=_TERRAFORM_KIND_TO_DB.get(body.run_kind or "plan", "plan"),
                status="queued",
                started_by_user_id=body.user_id or body.initiated_by_user_id,
                approved_by_user_id=body.approver_user_id,
                started_at=body.queued_at or body.started_at or datetime.utcnow(),
                experiment_id=body.experiment_id,
                test_id=body.test_id,
                owner_user_id=body.user_id or body.initiated_by_user_id,
                project_id=ws_row.project_id,
                workspace_id=ws_row.workspace_id,
            )
            session.add(existing)

        if body.phase == "start":
            existing.status = "running"
        elif body.phase == "finish":
            existing.status = _TERRAFORM_STATUS_TO_DB.get(body.status or "succeeded", "completed")
            existing.finished_at = body.finished_at or datetime.utcnow()
            existing.duration_ms = body.duration_ms
            if body.plan_summary:
                existing.plan_summary_json = dict(body.plan_summary)
            if body.error:
                existing.error = body.error[:8192]
            if body.halt_reason:
                existing.halted = True

        session.commit()
        run_db_id = existing.id

    logger.debug(
        "terraform-runs ingest persisted run_id=%s phase=%s actor=%s",
        run_db_id,
        body.phase,
        actor,
    )
    return {"ok": True, "persisted": True, "run_id": run_db_id, "phase": body.phase}


# ---------------------------------------------------------------------------
# /workload-runs ingest
# ---------------------------------------------------------------------------


@router.post("/workload-runs", include_in_schema=False)
def ingest_workload_run(
    body: WorkloadRunAuditPayload,
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """Persist a ``workload_runs`` row dispatched by the CP HTTP audit sink.

    Best-effort write — when the monolith's ``workload_runs`` ORM is
    unavailable (older deployment without Alembic 0055), the route
    returns ``persisted=False`` so the CP doesn't loop on retries.
    """
    claims = _require_m2m_bearer(authorization)
    actor = claims.get("sub") or claims.get("client_id") or "cp"

    try:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_workloads import (
            PostgresWorkloadAuditSink,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("workload-runs ingest: ORM unavailable (%s); dropping", exc)
        return {"ok": True, "persisted": False, "reason": "orm unavailable"}

    payload = body.model_dump(mode="json", exclude_none=True)
    payload.setdefault("run_id", str(uuid.uuid4()))

    try:
        with get_session() as session:
            sink = PostgresWorkloadAuditSink(session=session)
            sink.upsert_from_payload(payload)
            session.commit()
    except AttributeError:
        # PostgresWorkloadAuditSink may not yet expose upsert_from_payload
        # in older builds; degrade gracefully so rollouts can land the
        # CP side first and the monolith side in a follow-up.
        logger.warning(
            "workload-runs ingest: PostgresWorkloadAuditSink has no upsert_from_payload; dropping"
        )
        return {"ok": True, "persisted": False, "reason": "sink api mismatch"}
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "workload-runs ingest: persist failed for run_id=%s actor=%s: %s",
            payload.get("run_id"),
            actor,
            exc,
        )
        return {"ok": True, "persisted": False, "reason": "persist error"}

    return {"ok": True, "persisted": True, "run_id": payload.get("run_id")}


__all__ = ["router"]
