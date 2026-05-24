"""GET /admin/health - unauthenticated liveness probe."""
from __future__ import annotations

from fastapi import APIRouter

from aqp_admin import __version__

router = APIRouter(prefix="/admin", tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
