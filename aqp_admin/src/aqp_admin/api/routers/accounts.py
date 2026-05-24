"""GET/POST /admin/accounts/* - organizations, billing, tenancy.

Stub-only. Real implementations call the canonical AQP `data.tenancy.*` MCP
tools through the control plane and the billing provider in
`aqp_admin.providers`.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/admin/accounts", tags=["accounts"])


@router.get("/organizations")
async def list_organizations() -> dict[str, list[dict[str, str]]]:
    """List the organizations the caller can administer (stub)."""
    return {"organizations": []}


@router.get("/billing/summary")
async def billing_summary() -> dict[str, str]:
    """Aggregated billing summary across organizations (stub)."""
    raise HTTPException(status_code=501, detail="billing summary not implemented (stub)")


@router.get("/tenancy/invites")
async def list_invites() -> dict[str, list[dict[str, str]]]:
    """List pending tenancy invites (stub)."""
    return {"invites": []}
