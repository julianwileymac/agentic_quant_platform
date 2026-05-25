"""``/admin/services/*`` — managed-service catalog brokered to the CP."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from aqp_admin.deps.identity import AdminUser, require_admin
from aqp_admin.services.managed import ManagedServiceCatalog

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/services", tags=["services"])


@router.get(
    "",
    summary="List managed services across all tenant namespaces.",
)
async def list_services(
    namespace: str | None = None,
    user: AdminUser = Depends(require_admin),
) -> dict[str, list[dict[str, object]]]:
    catalog = ManagedServiceCatalog()
    services = await catalog.list(namespace=namespace)
    return {
        "services": [
            {
                "id": s.id,
                "kind": s.kind,
                "org_id": s.org_id,
                "namespace": s.namespace,
                "state": s.state,
                "phase": s.phase,
                "image": s.image,
                "replicas_desired": s.replicas_desired,
                "replicas_ready": s.replicas_ready,
            }
            for s in services
        ],
    }


__all__ = ["router"]
