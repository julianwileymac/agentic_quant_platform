"""``/manage/health`` + ``/manage/livez`` + ``/manage/readyz`` — control plane probes.

Phase 4b control-plane maturation. Three probes for the sidecar
control plane that mirror the AQP API:

- ``/manage/health`` — full diagnostic (kept for backward compatibility
  with existing dashboards).
- ``/manage/livez`` — Kubernetes liveness; no downstream calls.
- ``/manage/readyz`` — Kubernetes readiness; verifies the active
  :class:`InfrastructureProvider` is reachable before traffic is
  routed to this pod.
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Response, status

from aqp_cp import __version__
from aqp_cp.models import HealthStatus, ResponseEnvelope
from aqp_cp.settings import get_settings

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    summary="Full diagnostic probe (unauthenticated).",
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


@router.get(
    "/livez",
    summary="Liveness probe (no downstream calls).",
    description=(
        "Returns 200 the moment the FastAPI process is up. Performs no "
        "downstream calls. Wired into Kubernetes ``livenessProbe`` so "
        "transient provider outages don't trigger pod restarts."
    ),
)
async def livez() -> dict[str, Any]:
    return {"status": "alive", "service": "aqp-control-plane"}


@router.get(
    "/readyz",
    summary="Readiness probe (provider reachability).",
    description=(
        "Returns 200 only when the active :class:`InfrastructureProvider` "
        "is reachable; 503 otherwise. Wired into Kubernetes "
        "``readinessProbe`` so traffic only reaches pods that can "
        "actually drive workload operations."
    ),
)
async def readyz(response: Response) -> dict[str, Any]:
    settings = get_settings()
    checks: list[dict[str, Any]] = []

    # Provider reachability check
    t0 = time.perf_counter()
    try:
        from aqp_cp.services.lifecycle import get_active_provider

        provider = get_active_provider()
        # Cheap call — every provider exposes ``list_deployments`` with a
        # safe namespace argument; we don't care about the result, only
        # that the call completes.
        await provider.list_deployments(namespace=None)
        checks.append(
            {
                "name": f"provider:{settings.provider}",
                "status": "ok",
                "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append(
            {
                "name": f"provider:{settings.provider}",
                "status": "unreachable",
                "detail": str(exc)[:200],
            }
        )

    overall_ok = all(c["status"] in ("ok", "skipped") for c in checks)
    if not overall_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "checks": checks}
    return {"status": "ready", "checks": checks}


__all__ = ["router"]
