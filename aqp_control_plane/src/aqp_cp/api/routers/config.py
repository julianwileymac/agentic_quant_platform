"""``/manage/config`` — read / patch ConfigMaps."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header

from aqp_cp.auth.deps import AuthenticatedUser, require_scope
from aqp_cp.models import (
    ConfigMapPatch,
    ResponseEnvelope,
    ServiceConfig,
    WorkloadAction,
)
from aqp_cp.services.lifecycle import execute_with_audit, get_active_provider

router = APIRouter(tags=["config"])


@router.get(
    "/config/{service_id}",
    summary="Read the current (non-secret) configuration for ``service_id``.",
    response_model=ResponseEnvelope[ServiceConfig],
)
async def get_config(
    service_id: str,
    namespace: str | None = None,
    user: AuthenticatedUser = Depends(require_scope("read:infrastructure")),
) -> ResponseEnvelope[ServiceConfig]:
    provider = get_active_provider()
    cfg = await provider.get_config(service_id, namespace=namespace)
    return ResponseEnvelope(status="ok", data=cfg)


@router.patch(
    "/config/{service_id}",
    summary="Patch the ConfigMap backing ``service_id`` and optionally restart.",
    response_model=ResponseEnvelope[dict],
)
async def patch_config(
    service_id: str,
    patch: ConfigMapPatch,
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    user: AuthenticatedUser = Depends(require_scope("manage:infrastructure")),
) -> ResponseEnvelope[dict]:
    if patch.service_id != service_id:
        patch = patch.model_copy(update={"service_id": service_id})
    provider = get_active_provider()
    _run, applied = await execute_with_audit(
        action=WorkloadAction.APPLY_CONFIG,
        target=service_id,
        user=user,
        payload=patch.model_dump(mode="json"),
        fn=lambda: provider.apply_config(patch),
        request_id=x_request_id,
    )
    return ResponseEnvelope(
        status="ok",
        data={"applied": bool(applied), "service_id": service_id},
    )


__all__ = ["router"]
