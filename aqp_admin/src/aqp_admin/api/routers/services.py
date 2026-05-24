"""GET/POST /admin/services/* - managed-service catalog.

Stub-only. Real implementations broker to the control plane's
`/manage/deployments` and the topology service.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/admin/services", tags=["services"])


@router.get("")
async def list_services() -> dict[str, list[dict[str, str]]]:
    """List managed services that AQP exposes to customers (stub)."""
    return {"services": []}


@router.post("/{service_id}/provision")
async def provision(service_id: str) -> dict[str, str]:
    """Provision a managed service for a specific organization (stub)."""
    raise HTTPException(status_code=501, detail=f"provision({service_id}) not implemented (stub)")


@router.post("/{service_id}/suspend")
async def suspend(service_id: str) -> dict[str, str]:
    """Suspend a managed service (stub)."""
    raise HTTPException(status_code=501, detail=f"suspend({service_id}) not implemented (stub)")
