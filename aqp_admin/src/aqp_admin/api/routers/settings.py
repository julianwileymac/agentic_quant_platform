"""``/admin/settings`` — framework settings + cloud account onboarding.

Adds an admin-facing settings surface with audit-first mutations:

- ``GET /admin/settings/framework``                          (read current persisted + runtime config)
- ``PATCH /admin/settings/framework``                        (persist config patch via CP)
- ``GET /admin/settings/cloud/status``                       (providers + health snapshots)
- ``POST /admin/settings/cloud/providers``                   (connect AWS/Azure/GCP account)
- ``POST /admin/settings/cloud/cloudflare``                  (persist Cloudflare account settings)

All mutating routes write the audit ``start`` row before broker dispatch and
finalise with ``succeeded`` / ``failed`` after.
"""
from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from aqp_admin.deps.audit import AuditContext, audit_context_dep
from aqp_admin.deps.identity import AdminUser, require_admin_scope
from aqp_admin.integrations import AdminBrokerError, get_brokers
from aqp_admin.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/settings", tags=["settings"])


def _bearer_from_header(header_value: str | None) -> str | None:
    if not header_value or not header_value.lower().startswith("bearer "):
        return None
    return header_value.split(None, 1)[1].strip()


def _runtime_settings_payload() -> dict[str, Any]:
    settings = get_settings()
    return {
        "api_url": settings.api_url,
        "control_plane_url": settings.control_plane_url,
        "cors_origins": list(settings.cors_origins),
        "auth_required": settings.auth_required,
        "auth_provider": settings.auth_provider,
        "auth_entra_tenant": settings.auth_entra_tenant,
        "auth_oidc_audience": settings.auth_oidc_audience,
        "auth_claims_namespace": settings.auth_claims_namespace,
        "audit_sink": settings.audit_sink,
        "audit_jsonl_path": settings.audit_jsonl_path,
        "m2m_credential_service": settings.m2m_credential_service,
        "m2m_credential_purpose": settings.m2m_credential_purpose,
        "m2m_cp_audience": settings.m2m_cp_audience,
    }


class FrameworkPatchBody(BaseModel):
    service_id: str = Field(default="aqp-admin", min_length=1)
    namespace: str | None = None
    values: dict[str, str] = Field(default_factory=dict)
    delete_keys: list[str] = Field(default_factory=list)
    secret_refs: list[dict[str, Any]] = Field(default_factory=list)
    trigger_restart: bool = True


class CloudProviderConnectBody(BaseModel):
    provider_kind: Literal["aws", "azure", "gcp"]
    slug: str = Field(..., min_length=1, max_length=80)
    name: str = Field(..., min_length=1, max_length=240)
    default_region: str | None = Field(default=None, max_length=64)
    credential_key: str | None = Field(default=None, max_length=240)
    config_json: dict[str, Any] = Field(default_factory=dict)


class CloudflareConnectBody(BaseModel):
    service_id: str = Field(default="aqp-admin", min_length=1)
    namespace: str | None = None
    account_id: str = Field(..., min_length=1, max_length=120)
    zone_id: str | None = Field(default=None, max_length=120)
    team_domain: str | None = Field(default=None, max_length=240)
    trigger_restart: bool = True


@router.get(
    "/framework",
    summary="Read framework settings (runtime + persisted config map).",
)
async def get_framework_settings(
    service_id: str = "aqp-admin",
    namespace: str | None = None,
    user: AdminUser = Depends(require_admin_scope("read:infrastructure")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    bearer = _bearer_from_header(authorization)
    config: dict[str, Any] | None = None
    config_error: dict[str, Any] | None = None
    try:
        payload = await get_brokers().control_plane.get_config(
            service_id,
            namespace=namespace,
            bearer_passthrough=bearer,
        )
        if isinstance(payload, dict):
            config = payload.get("data") if "data" in payload else payload
    except AdminBrokerError as exc:
        config_error = {
            "code": exc.code,
            "status_code": exc.status_code,
            "error_description": str(exc),
        }
    return {
        "service_id": service_id,
        "namespace": namespace,
        "runtime_settings": _runtime_settings_payload(),
        "persisted_config": config,
        "persisted_config_error": config_error,
    }


@router.patch(
    "/framework",
    summary="Persist framework settings through the control-plane config patch route.",
)
async def patch_framework_settings(
    body: FrameworkPatchBody,
    user: AdminUser = Depends(require_admin_scope("manage:infrastructure")),
    audit: AuditContext = Depends(audit_context_dep("admin.settings.framework.patch")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    audit.target = body.service_id
    audit.start(payload=body.model_dump())
    bearer = _bearer_from_header(authorization)
    patch_body = {
        "service_id": body.service_id,
        "values": body.values,
        "delete_keys": body.delete_keys,
        "secret_refs": body.secret_refs,
        "trigger_restart": body.trigger_restart,
    }
    try:
        result = await get_brokers().control_plane.patch_config(
            body.service_id,
            patch_body,
            namespace=body.namespace,
            bearer_passthrough=bearer,
        )
    except AdminBrokerError as exc:
        audit.fail(str(exc))
        raise HTTPException(
            status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            detail={"error": exc.code, "error_description": str(exc)},
        ) from exc
    audit.succeed({"service_id": body.service_id, "namespace": body.namespace})
    return {
        "service_id": body.service_id,
        "namespace": body.namespace,
        "result": result,
        "audit_run_id": audit.run_id,
    }


@router.get(
    "/cloud/status",
    summary="Cloud onboarding status (connected providers + health snapshots).",
)
async def cloud_status(
    user: AdminUser = Depends(require_admin_scope("read:infrastructure")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    bearer = _bearer_from_header(authorization)
    brokers = get_brokers()
    errors: list[dict[str, Any]] = []
    terraform_providers: list[dict[str, Any]] = []
    cp_health: dict[str, Any] | None = None
    cloudflare_health: dict[str, Any] | None = None

    try:
        payload = await brokers.monolith.list_terraform_providers(
            bearer_passthrough=bearer
        )
        items = payload.get("items") if isinstance(payload, dict) else None
        if isinstance(items, list):
            terraform_providers = [
                item
                for item in items
                if isinstance(item, dict)
                and item.get("kind") in {"aws", "azure", "gcp"}
            ]
    except AdminBrokerError as exc:
        errors.append(
            {
                "surface": "terraform.providers",
                "code": exc.code,
                "status_code": exc.status_code,
                "error_description": str(exc),
            }
        )

    try:
        cp_health_payload = await brokers.control_plane.telemetry_snapshot(
            bearer_passthrough=bearer
        )
        if isinstance(cp_health_payload, dict):
            cp_health = (
                cp_health_payload.get("data")
                if "data" in cp_health_payload
                else cp_health_payload
            )
    except AdminBrokerError as exc:
        errors.append(
            {
                "surface": "control_plane.telemetry",
                "code": exc.code,
                "status_code": exc.status_code,
                "error_description": str(exc),
            }
        )

    try:
        cloudflare_health = await brokers.monolith.cloudflare_health(
            bearer_passthrough=bearer
        )
    except AdminBrokerError as exc:
        errors.append(
            {
                "surface": "cloudflare.health",
                "code": exc.code,
                "status_code": exc.status_code,
                "error_description": str(exc),
            }
        )

    return {
        "terraform_providers": terraform_providers,
        "control_plane_health": cp_health,
        "cloudflare_health": cloudflare_health,
        "errors": errors,
    }


@router.post(
    "/cloud/providers",
    summary="Connect AWS/Azure/GCP account via Terraform provider registry.",
)
async def connect_cloud_provider(
    body: CloudProviderConnectBody,
    user: AdminUser = Depends(require_admin_scope("admin:cluster")),
    audit: AuditContext = Depends(audit_context_dep("admin.settings.cloud.provider.connect")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    audit.target = f"{body.provider_kind}:{body.slug}"
    audit.start(payload=body.model_dump())
    bearer = _bearer_from_header(authorization)
    payload = {
        "slug": body.slug,
        "name": body.name,
        "kind": body.provider_kind,
        "default_region": body.default_region,
        "config_json": body.config_json,
        "credential_key": body.credential_key,
    }
    try:
        result = await get_brokers().monolith.create_terraform_provider(
            payload,
            bearer_passthrough=bearer,
        )
    except AdminBrokerError as exc:
        audit.fail(str(exc))
        raise HTTPException(
            status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            detail={"error": exc.code, "error_description": str(exc)},
        ) from exc
    audit.succeed({"provider_kind": body.provider_kind, "slug": body.slug})
    return {"provider": result, "audit_run_id": audit.run_id}


@router.post(
    "/cloud/cloudflare",
    summary="Persist Cloudflare account settings and run a health check.",
)
async def connect_cloudflare(
    body: CloudflareConnectBody,
    user: AdminUser = Depends(require_admin_scope("admin:cluster")),
    audit: AuditContext = Depends(audit_context_dep("admin.settings.cloud.cloudflare.connect")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    audit.target = body.service_id
    audit.start(payload={"service_id": body.service_id, "namespace": body.namespace})
    bearer = _bearer_from_header(authorization)
    values: dict[str, str] = {"CLOUDFLARE_ACCOUNT_ID": body.account_id}
    if body.zone_id:
        values["CLOUDFLARE_ZONE_ID"] = body.zone_id
    if body.team_domain:
        values["CLOUDFLARE_TEAM_DOMAIN"] = body.team_domain
    patch_body = {
        "service_id": body.service_id,
        "values": values,
        "delete_keys": [],
        "secret_refs": [],
        "trigger_restart": body.trigger_restart,
    }

    try:
        config_result = await get_brokers().control_plane.patch_config(
            body.service_id,
            patch_body,
            namespace=body.namespace,
            bearer_passthrough=bearer,
        )
    except AdminBrokerError as exc:
        audit.fail(str(exc))
        raise HTTPException(
            status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            detail={"error": exc.code, "error_description": str(exc)},
        ) from exc

    health_payload: dict[str, Any] | None = None
    health_error: dict[str, Any] | None = None
    try:
        health_payload = await get_brokers().monolith.cloudflare_health(
            bearer_passthrough=bearer
        )
    except AdminBrokerError as exc:
        health_error = {
            "code": exc.code,
            "status_code": exc.status_code,
            "error_description": str(exc),
        }

    audit.succeed(
        {
            "service_id": body.service_id,
            "namespace": body.namespace,
            "cloudflare_health_ok": health_error is None,
        }
    )
    return {
        "service_id": body.service_id,
        "namespace": body.namespace,
        "config_result": config_result,
        "cloudflare_health": health_payload,
        "cloudflare_health_error": health_error,
        "audit_run_id": audit.run_id,
    }


__all__ = ["router"]
