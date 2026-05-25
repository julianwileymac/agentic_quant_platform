"""``/manage/tenants`` — per-tenant namespace bootstrap.

Implements Phase 1.1 of the control-plane maturation plan:

- ``POST /manage/tenants/{tenant_id}/provision`` — SSA the Namespace +
  ResourceQuota + LimitRange + NetworkPolicy bundle.
- ``GET  /manage/tenants/{tenant_id}`` — read the rendered SSA inputs
  for diagnostic + UI display.
- ``DELETE /manage/tenants/{tenant_id}`` — admin-only teardown
  (cascading delete of the tenant namespace).

Mutations route through :class:`WorkloadRuntime` so the action lands
in the ``workload_runs`` audit ledger BEFORE the SSA call dispatches
(AGENTS rule 45). Scope-wise:

- ``manage:tenants`` for provision (rule 52: step-up required when
  the cookie cutter is wired into the admin UI).
- ``read:infrastructure`` for the GET endpoints.
- ``admin:cluster`` for the DELETE.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from aqp_platform_core.models.tenancy import (
    TenantNamespaceSpec,
    TenantNamespaceStatus,
)
from aqp_platform_core.models.workloads import WorkloadAction
from aqp_platform_core.runtime.workload import WorkloadRequestContext

from aqp_cp.auth.deps import AuthenticatedUser, require_scope
from aqp_cp.builders.tenant import render_tenant_namespace_objects
from aqp_cp.models import ResponseEnvelope
from aqp_cp.services.lifecycle import (
    execute_with_audit,
    get_active_provider,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tenants"], prefix="/tenants")


@router.post(
    "/{tenant_id}/provision",
    summary="Provision (or update) a tenant's Kubernetes namespace bundle.",
    description=(
        "Server-side-applies the four / five canonical tenant objects "
        "(Namespace + ResourceQuota + LimitRange + NetworkPolicy "
        "default-deny + optional intra-tenant allow). Idempotent. "
        "Required scope: ``manage:tenants`` (admin:cluster bypass). "
        "The UI should friction-gate this with a step-up MFA prompt."
    ),
    response_model=ResponseEnvelope[TenantNamespaceStatus],
)
async def provision_tenant(
    tenant_id: str,
    spec: TenantNamespaceSpec,
    request: Request,
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    user: AuthenticatedUser = Depends(require_scope("manage:tenants")),
) -> ResponseEnvelope[TenantNamespaceStatus]:
    if spec.tenant_id != tenant_id:
        spec = spec.model_copy(update={"tenant_id": tenant_id})
    provider = get_active_provider()
    _run, result = await execute_with_audit(
        action=WorkloadAction.PROVISION_TENANT,
        target=spec.namespace(),
        user=user,
        payload=spec.model_dump(mode="json"),
        fn=lambda: provider.provision_tenant_namespace(spec),
        request_id=x_request_id,
    )
    return ResponseEnvelope(status="ok", data=result)


@router.get(
    "/{tenant_id}/render",
    summary="Render the SSA bundle without applying it.",
    description=(
        "Returns the list of Kubernetes object dicts the provision "
        "endpoint would server-side-apply. Useful for diff preview "
        "in the admin UI. Read-only — does NOT touch the cluster. "
        "Required scope: ``read:infrastructure``."
    ),
    response_model=ResponseEnvelope[list[dict[str, Any]]],
)
async def render_tenant_bundle(
    tenant_id: str,
    spec: TenantNamespaceSpec,
    user: AuthenticatedUser = Depends(require_scope("read:infrastructure")),
) -> ResponseEnvelope[list[dict[str, Any]]]:
    if spec.tenant_id != tenant_id:
        spec = spec.model_copy(update={"tenant_id": tenant_id})
    objects = render_tenant_namespace_objects(spec)
    return ResponseEnvelope(status="ok", data=objects)


@router.get(
    "/{tenant_id}",
    summary="Probe the live status of a tenant's namespace.",
    description=(
        "Best-effort probe — returns the namespace label + quota usage "
        "as the provider sees them. Returns 404 when the namespace "
        "doesn't exist. Required scope: ``read:infrastructure``."
    ),
    response_model=ResponseEnvelope[dict[str, Any]],
)
async def get_tenant(
    tenant_id: str,
    namespace_prefix: str = "tenant",
    user: AuthenticatedUser = Depends(require_scope("read:infrastructure")),
) -> ResponseEnvelope[dict[str, Any]]:
    provider = get_active_provider()
    namespace = f"{namespace_prefix}-{tenant_id}"
    try:
        deployments = await provider.list_deployments(namespace=namespace)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "tenant_namespace_not_found",
                "error_description": str(exc),
                "tenant_id": tenant_id,
                "namespace": namespace,
            },
        ) from exc
    return ResponseEnvelope(
        status="ok",
        data={
            "tenant_id": tenant_id,
            "namespace": namespace,
            "deployment_count": len(deployments),
            "deployments": [d.model_dump() for d in deployments],
        },
    )


@router.delete(
    "/{tenant_id}",
    summary="Tear down a tenant's namespace (admin:cluster only).",
    description=(
        "Cascading delete of the Namespace and every object inside it "
        "(Deployments, ConfigMaps, Secrets, PVCs, NetworkPolicies, "
        "etc.). Step-up MFA required in production. Required scope: "
        "``admin:cluster``."
    ),
    response_model=ResponseEnvelope[TenantNamespaceStatus],
)
async def delete_tenant(
    tenant_id: str,
    request: Request,
    namespace_prefix: str = "tenant",
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    user: AuthenticatedUser = Depends(require_scope("admin:cluster")),
) -> ResponseEnvelope[TenantNamespaceStatus]:
    provider = get_active_provider()
    _run, result = await execute_with_audit(
        action=WorkloadAction.DEPROVISION_TENANT,
        target=f"{namespace_prefix}-{tenant_id}",
        user=user,
        payload={"tenant_id": tenant_id, "namespace_prefix": namespace_prefix},
        fn=lambda: provider.deprovision_tenant_namespace(
            tenant_id, namespace_prefix=namespace_prefix
        ),
        request_id=x_request_id,
    )
    return ResponseEnvelope(status="ok", data=result)


__all__ = ["router"]
