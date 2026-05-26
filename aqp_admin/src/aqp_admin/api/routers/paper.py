# ruff: noqa: B008, ARG001
"""``/admin/paper`` — paper-trading control surface.

Wraps the monolith's ``/paper/*`` REST surface so the admin BFF has
its own audit-first path for paper-trading lifecycle. The KillSwitch
fan-out (``/admin/halt/all``) already targets ``/paper/stop-all`` for
emergency halts; this module adds:

- list / read of paper-trading runs (``PaperTradingRun`` rows)
- start a new run from a YAML-backed config name (``configs/paper/<name>.yaml``)
- stop a single run by id
- subscribe-url for the WebSocket progress stream

Per the canonical ``configs/paper/README.md`` contract, paper sessions
are long-running Celery tasks owned by the monolith. The admin surface
NEVER spawns a session inline — it always brokers to the monolith's
``POST /paper/runs`` endpoint.
"""
from __future__ import annotations

from typing import Any, NoReturn

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from aqp_admin.deps.audit import AuditContext, audit_context_dep
from aqp_admin.deps.identity import AdminUser, require_admin_scope
from aqp_admin.deps.stepup import require_admin_step_up
from aqp_admin.integrations import AdminBrokerError, get_brokers

router = APIRouter(prefix="/admin/paper", tags=["paper-trading"])


def _bearer_from_header(header_value: str | None) -> str | None:
    if not header_value or not header_value.lower().startswith("bearer "):
        return None
    return header_value.split(None, 1)[1].strip()


def _raise_broker_error(exc: AdminBrokerError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
        detail={"error": exc.code, "error_description": str(exc)},
    ) from exc


class StartRunBody(BaseModel):
    config_name: str = Field(..., min_length=1, max_length=240)
    dry_run: bool = Field(
        default=False,
        description=(
            "When True the engine routes orders through the deterministic "
            "replay broker instead of a live exchange. Mirrors the "
            "session.dry_run flag in the YAML config."
        ),
    )
    reason: str = Field(..., min_length=4, max_length=200)


class StopRunBody(BaseModel):
    reason: str = Field(..., min_length=4, max_length=200)
    cancel_open_orders: bool = Field(default=True)


@router.get("/runs", summary="List paper-trading runs.")
async def list_runs(
    organization_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=500),
    user: AdminUser = Depends(require_admin_scope("trade:read")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """List paper-trading runs. Filters by ``organization_id`` and
    ``status`` (``pending|running|halted|completed|failed``)."""
    try:
        return await get_brokers().monolith.list_paper_runs(
            organization_id=organization_id,
            status=status_filter,
            limit=limit,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


@router.get("/runs/{run_id}", summary="Describe one paper-trading run.")
async def describe_run(
    run_id: str,
    user: AdminUser = Depends(require_admin_scope("trade:read")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    try:
        return await get_brokers().monolith.get_paper_run(
            run_id,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


@router.get(
    "/runs/{run_id}/stream-url",
    summary="Subscribe URL for the paper-run progress stream.",
)
async def stream_url(
    run_id: str,
    user: AdminUser = Depends(require_admin_scope("trade:read")),
) -> dict[str, Any]:
    """Return the WebSocket URL for the paper-run progress stream.

    The actual WebSocket lives on the monolith — the admin surface
    just hands the URL to the SPA so its `useChannel` hook can
    connect directly.
    """
    return {
        "stream_url": f"/chat/stream/{run_id}",
        "channel": f"paper.{run_id}",
    }


@router.post(
    "/runs",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start a paper-trading run.",
)
async def start_run(
    body: StartRunBody,
    user: AdminUser = Depends(
        require_admin_step_up("trade:execute", max_age_seconds=180),
    ),
    audit: AuditContext = Depends(audit_context_dep("admin.paper.start")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """Submit a paper-trading run via the monolith.

    Step-up gated per AGENTS rule 52 — even though paper trading
    does not move real capital, a paper session can saturate broker
    rate limits and produce confusing audit signals when triggered
    by an unattended automation.
    """
    audit.target = body.config_name
    audit.start(payload=body.model_dump())
    try:
        result = await get_brokers().monolith.start_paper_run(
            config_name=body.config_name,
            dry_run=body.dry_run,
            reason=body.reason,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        audit.fail(str(exc))
        _raise_broker_error(exc)
    audit.succeed({"task_id": result.get("task_id"), "run_id": result.get("run_id")})
    return {"result": result, "audit_run_id": audit.run_id}


@router.post(
    "/runs/{run_id}/stop",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Stop a paper-trading run.",
)
async def stop_run(
    run_id: str,
    body: StopRunBody,
    user: AdminUser = Depends(
        require_admin_step_up("trade:execute", "deploy:halt", max_age_seconds=180),
    ),
    audit: AuditContext = Depends(audit_context_dep("admin.paper.stop")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """Stop a single paper-trading run.

    Use ``POST /admin/halt/all`` if you need to stop ALL paper +
    bot + RL + agent runs in one shot — that fans out to every
    halt endpoint in parallel.
    """
    audit.target = run_id
    audit.start(payload=body.model_dump())
    try:
        result = await get_brokers().monolith.stop_paper_run(
            run_id,
            reason=body.reason,
            cancel_open_orders=body.cancel_open_orders,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        audit.fail(str(exc))
        _raise_broker_error(exc)
    audit.succeed({"run_id": run_id, "stopped": True})
    return {"result": result, "audit_run_id": audit.run_id}


__all__ = ["router"]
