"""``/manage/health`` — unauthenticated readiness probe."""
from __future__ import annotations

from fastapi import APIRouter

from aqp_cp import __version__
from aqp_cp.models import HealthStatus, ResponseEnvelope
from aqp_cp.settings import get_settings

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    summary="Readiness probe (unauthenticated).",
    description=(
        "Returns ``{status: ok, data: ...}`` when the control plane has "
        "successfully loaded its settings. Used by Kubernetes liveness/"
        "readiness probes and docker-compose healthcheck."
    ),
    responses={
        200: {"description": "Control plane is up."},
        503: {"description": "Reserved — not currently emitted."},
    },
)
async def health() -> ResponseEnvelope[dict]:
    settings = get_settings()
    return ResponseEnvelope(
        status="ok",
        data={
            "service": "aqp-control-plane",
            "version": __version__,
            "status": HealthStatus.OK.value,
            "provider": settings.provider,
            "auth_enabled": settings.auth_enabled,
        },
    )


__all__ = ["router"]
