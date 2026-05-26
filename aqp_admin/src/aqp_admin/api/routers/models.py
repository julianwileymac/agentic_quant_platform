# ruff: noqa: B008, ARG001
"""``/admin/models`` — MLflow model registry surface.

Wraps the existing MLflow REST API by brokering through the monolith
(it owns the MLflow client + the `aqp_models.tasks.*` Celery tasks).
The admin surface offers read views + the champion/challenger
promotion workflow.

Promotion goes through step-up MFA per AGENTS rule 52 — alias moves
in production change live trading inference.
"""
from __future__ import annotations

from typing import Any, Literal, NoReturn

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from aqp_admin.deps.audit import AuditContext, audit_context_dep
from aqp_admin.deps.identity import AdminUser, require_admin_scope
from aqp_admin.deps.stepup import require_admin_step_up
from aqp_admin.integrations import AdminBrokerError, get_brokers

router = APIRouter(prefix="/admin/models", tags=["models"])


def _bearer_from_header(header_value: str | None) -> str | None:
    if not header_value or not header_value.lower().startswith("bearer "):
        return None
    return header_value.split(None, 1)[1].strip()


def _raise_broker_error(exc: AdminBrokerError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
        detail={"error": exc.code, "error_description": str(exc)},
    ) from exc


class AliasBody(BaseModel):
    """Champion/challenger alias mutation.

    Aliases are MLflow's canonical way to mark a version
    "champion" / "challenger" / "production"; we limit the surface
    to the three documented aqp_models aliases plus a free-form
    catch-all that operators can use during experimentation.
    """

    version: int = Field(..., ge=1)
    alias: Literal["champion", "challenger", "production", "experimental", "shadow"]
    reason: str = Field(..., min_length=4, max_length=200)


@router.get("", summary="List registered models.")
async def list_models(
    namespace: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    user: AdminUser = Depends(require_admin_scope("ml:workbench")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """List registered models with summary metadata.

    Filters by ``namespace`` so the operator can scope to a single
    quant team. Response carries ``name``, ``creation_timestamp``,
    ``last_updated_timestamp``, ``latest_versions`` summary, and
    ``aliases`` map.
    """
    try:
        return await get_brokers().monolith.list_mlflow_models(
            namespace=namespace,
            limit=limit,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


@router.get("/{name}", summary="Describe a model.")
async def describe_model(
    name: str,
    user: AdminUser = Depends(require_admin_scope("ml:workbench")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """Describe a registered model — full alias map + tag set."""
    try:
        return await get_brokers().monolith.describe_mlflow_model(
            name,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


@router.get("/{name}/versions", summary="List versions for a model.")
async def list_versions(
    name: str,
    limit: int = Query(default=50, ge=1, le=500),
    user: AdminUser = Depends(require_admin_scope("ml:workbench")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """List versions for a model with run metadata + alpha-backtest links."""
    try:
        return await get_brokers().monolith.list_mlflow_versions(
            name,
            limit=limit,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


@router.get("/{name}/versions/{version}", summary="Describe a model version.")
async def describe_version(
    name: str,
    version: int,
    user: AdminUser = Depends(require_admin_scope("ml:workbench")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """Describe one model version including distillation lineage."""
    try:
        return await get_brokers().monolith.describe_mlflow_version(
            name,
            version,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


@router.put(
    "/{name}/aliases/{alias}",
    summary="Set the model alias to a specific version.",
)
async def set_alias(
    name: str,
    alias: str,
    body: AliasBody,
    user: AdminUser = Depends(
        require_admin_step_up("ml:workbench", "platform:admin", max_age_seconds=180),
    ),
    audit: AuditContext = Depends(audit_context_dep("admin.models.set_alias")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """Move an MLflow alias to a different version.

    Champion/challenger flips are step-up gated per AGENTS rule 52.
    The audit row carries the prior alias mapping so a rollback can
    be reconstructed from the ledger alone.
    """
    if alias != body.alias:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "alias_mismatch",
                "error_description": "URL alias must match body.alias",
            },
        )
    audit.target = f"{name}:{alias}"
    audit.start(payload={"version": body.version, "reason": body.reason})
    try:
        result = await get_brokers().monolith.set_mlflow_alias(
            name,
            alias=alias,
            version=body.version,
            reason=body.reason,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        audit.fail(str(exc))
        _raise_broker_error(exc)
    audit.succeed(
        {
            "name": name,
            "alias": alias,
            "version": body.version,
            "previous_version": result.get("previous_version"),
        }
    )
    return {"result": result, "audit_run_id": audit.run_id}


@router.delete(
    "/{name}/aliases/{alias}",
    summary="Remove an alias.",
)
async def delete_alias(
    name: str,
    alias: str,
    user: AdminUser = Depends(
        require_admin_step_up("ml:workbench", "platform:admin", max_age_seconds=180),
    ),
    audit: AuditContext = Depends(audit_context_dep("admin.models.delete_alias")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """Remove an alias entirely. Step-up gated."""
    audit.target = f"{name}:{alias}"
    audit.start(payload={})
    try:
        result = await get_brokers().monolith.delete_mlflow_alias(
            name,
            alias=alias,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        audit.fail(str(exc))
        _raise_broker_error(exc)
    audit.succeed({"name": name, "alias": alias})
    return {"result": result, "audit_run_id": audit.run_id}


__all__ = ["router"]
