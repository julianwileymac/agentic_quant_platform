"""``/admin/tenants`` — tenant-vending wizard backend.

The admin UI ``/accounts/new`` route POSTs to ``/admin/tenants`` with
a single composite payload (org info + plan + Entra link or Auth0
org create + namespace spec). The handler:

1. Writes a ``status=pending`` audit row BEFORE any upstream call.
2. (B2B) Brokers a ``data.tenancy.link_org_to_entra_tenant`` call to
   the monolith if an Entra tenant id is supplied.
3. Brokers a ``POST /manage/tenants/{tenant_id}/provision`` to the
   CP using the rendered namespace spec.
4. Optionally brokers a ``POST /manage/terraform/workspaces/{ws}/apply``
   when the wizard ticks "hosted PaaS" (deferred to follow-up; the
   skeleton just logs the intent).

All four phases are best-effort + audit-tracked individually so a
partial failure produces a clear remediation path in the audit ledger.
"""
from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from aqp_platform_core.models.tenancy import TenantNamespaceSpec, TenantPlan

from aqp_admin.accounts.tenancy import TenancyService
from aqp_admin.deps.audit import AuditContext, audit_context_dep
from aqp_admin.deps.identity import AdminUser, require_admin_scope
from aqp_admin.integrations import AdminBrokerError, get_brokers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/tenants", tags=["tenants"])


class TenantVendingBody(BaseModel):
    org_id: str = Field(..., min_length=1, pattern=r"^[a-z0-9-]+$")
    org_name: str = Field(..., min_length=1)
    plan: Literal["b2b", "b2c", "internal", "sandbox"] = "b2b"
    entra_tenant_id: str | None = Field(
        default=None,
        description="Microsoft Entra tenant id to link the new Organization to (B2B).",
    )
    namespace_spec: TenantNamespaceSpec | None = Field(
        default=None,
        description=(
            "Optional explicit namespace spec. When omitted the wizard "
            "derives one from the plan + org_id."
        ),
    )
    enable_paas_terraform: bool = Field(
        default=False,
        description=(
            "When true the wizard also kicks off the hosted PaaS "
            "Terraform stack through the control plane."
        ),
    )
    terraform_workspace_id: str | None = Field(
        default=None,
        description="Control-plane Terraform workspace id for hosted-PaaS provisioning.",
    )
    terraform_spec: dict[str, Any] | None = Field(
        default=None,
        description=(
            "TerraformStackSpec payload to send to the control plane. "
            "Required when enable_paas_terraform is true."
        ),
    )


class TenantVendingResponse(BaseModel):
    org_id: str
    plan: str
    phases: list[dict[str, Any]]
    audit_run_id: str | None
    success: bool


def _bearer_from_header(header_value: str | None) -> str | None:
    if not header_value or not header_value.lower().startswith("bearer "):
        return None
    return header_value.split(None, 1)[1].strip()


@router.post(
    "",
    summary="Run the tenant-vending wizard (audit-first).",
    response_model=TenantVendingResponse,
)
async def vend_tenant(
    body: TenantVendingBody,
    user: AdminUser = Depends(require_admin_scope("manage:tenants")),
    audit: AuditContext = Depends(audit_context_dep("admin.tenants.vend")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> TenantVendingResponse:
    audit.target = body.org_id
    audit.start(
        payload={
            "org_id": body.org_id,
            "org_name": body.org_name,
            "plan": body.plan,
            "entra_tenant_id": body.entra_tenant_id,
            "namespace_spec_present": body.namespace_spec is not None,
            "enable_paas_terraform": body.enable_paas_terraform,
            "terraform_workspace_id": body.terraform_workspace_id,
            "terraform_spec_present": body.terraform_spec is not None,
        }
    )
    bearer = _bearer_from_header(authorization)
    phases: list[dict[str, Any]] = []
    success = True

    brokers = get_brokers()
    tenancy = TenancyService(monolith=brokers.monolith)

    # Phase 1: link Entra tenant (B2B) if supplied.
    if body.plan == "b2b" and body.entra_tenant_id:
        try:
            link = await tenancy.link_org_to_entra_tenant(
                org_id=body.org_id,
                tenant_id=body.entra_tenant_id,
                bearer_passthrough=bearer,
            )
            phases.append({
                "phase": "entra_link",
                "status": "succeeded" if link else "skipped",
                "link_id": link.id if link else None,
            })
        except Exception as exc:  # noqa: BLE001
            success = False
            phases.append({"phase": "entra_link", "status": "failed", "error": str(exc)})
            logger.exception("entra_link phase failed for %s", body.org_id)

    # Phase 2: namespace provision via the CP.
    spec = body.namespace_spec or TenantNamespaceSpec(
        tenant_id=body.org_id,
        plan=TenantPlan(body.plan),
    )
    try:
        result = await brokers.control_plane.provision_tenant(
            body.org_id, spec.model_dump(mode="json")
        )
        phases.append({
            "phase": "namespace_provision",
            "status": "succeeded",
            "result": result.get("data") if isinstance(result, dict) else result,
        })
    except AdminBrokerError as exc:
        success = False
        phases.append(
            {
                "phase": "namespace_provision",
                "status": "failed",
                "error": str(exc),
                "code": exc.code,
            }
        )
        logger.exception("namespace_provision phase failed for %s", body.org_id)

    # Phase 3: optional hosted PaaS Terraform through the CP TerraformRuntime.
    if body.enable_paas_terraform:
        if not body.terraform_workspace_id or not body.terraform_spec:
            success = False
            phases.append(
                {
                    "phase": "paas_terraform",
                    "status": "failed",
                    "error": "terraform_workspace_id and terraform_spec are required",
                    "remediation": (
                        "Select a Terraform workspace and stack version in the "
                        "admin UI, then retry the hosted-PaaS phase."
                    ),
                }
            )
        else:
            try:
                result = await brokers.control_plane.terraform_run(
                    body.terraform_workspace_id,
                    "apply",
                    {
                        "spec": body.terraform_spec,
                        "extra_args": [],
                    },
                    bearer_passthrough=bearer,
                )
                phases.append(
                    {
                        "phase": "paas_terraform",
                        "status": "succeeded",
                        "workspace_id": body.terraform_workspace_id,
                        "result": result.get("data") if isinstance(result, dict) else result,
                    }
                )
            except AdminBrokerError as exc:
                success = False
                phases.append(
                    {
                        "phase": "paas_terraform",
                        "status": "failed",
                        "error": str(exc),
                        "code": exc.code,
                    }
                )
                logger.exception("paas_terraform phase failed for %s", body.org_id)

    if success:
        audit.succeed({"phases": phases})
    else:
        audit.fail("one or more vending phases failed")
    return TenantVendingResponse(
        org_id=body.org_id,
        plan=body.plan,
        phases=phases,
        audit_run_id=audit.run_id,
        success=success,
    )


@router.get(
    "/{org_id}",
    summary="Read tenant namespace status from the CP.",
)
async def get_tenant(
    org_id: str,
    user: AdminUser = Depends(require_admin_scope("read:infrastructure")),
) -> dict[str, Any]:
    try:
        payload = await get_brokers().control_plane.tenant_status(org_id)
    except AdminBrokerError as exc:
        raise HTTPException(
            status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": exc.code,
                "error_description": str(exc),
                "org_id": org_id,
            },
        ) from exc
    return payload


__all__ = ["router"]
