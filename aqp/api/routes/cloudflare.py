"""``/cloudflare/*`` — runtime CRUD for Cloudflare tunnels, Access apps, DNS.

All routes require ``cluster:admin`` scope (the Management Engine
admin role). The active :class:`aqp.cloudflare.CloudflareEdgeAdapter`
holds the SDK client; this module is a thin REST envelope around it,
matching the shape of :mod:`aqp.api.routes.cluster_mgmt`.

Mutations write a ``workload_runs`` row via
:class:`aqp_platform_core.runtime.WorkloadRuntime` (when wired in
Phase E); for Phase D the routes simply call the adapter directly and
log structured audit events.
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from aqp.api.security import require_scope, secure_router
from aqp.cloudflare import (
    CloudflareAdapterError,
    CloudflareAdapterUnavailable,
    get_cloudflare_adapter,
)

logger = logging.getLogger(__name__)


router = secure_router(prefix="/cloudflare", tags=["cloudflare", "edge"])


def _wrap_unavailable(exc: CloudflareAdapterUnavailable) -> HTTPException:
    return HTTPException(status_code=503, detail=str(exc))


def _wrap_error(exc: CloudflareAdapterError) -> HTTPException:
    return HTTPException(status_code=502, detail=str(exc))


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@router.get(
    "/health",
    dependencies=[Depends(require_scope("cluster:read"))],
)
def cf_health() -> dict[str, Any]:
    return get_cloudflare_adapter().health()


# ---------------------------------------------------------------------------
# Tunnels
# ---------------------------------------------------------------------------


@router.get(
    "/tunnels",
    dependencies=[Depends(require_scope("cluster:read"))],
)
def list_tunnels(name: str | None = None) -> list[dict[str, Any]]:
    try:
        items = get_cloudflare_adapter().list_tunnels(name=name)
    except CloudflareAdapterUnavailable as exc:
        raise _wrap_unavailable(exc) from exc
    except CloudflareAdapterError as exc:
        raise _wrap_error(exc) from exc
    return [asdict(t) for t in items]


class CreateTunnelBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    config_src: str = Field(
        default="cloudflare",
        description="'cloudflare' (managed via dashboard) or 'local' (YAML on origin).",
    )


@router.post(
    "/tunnels",
    dependencies=[Depends(require_scope("cluster:admin"))],
)
def create_tunnel(body: CreateTunnelBody) -> dict[str, Any]:
    try:
        created = get_cloudflare_adapter().create_tunnel(
            name=body.name, config_src=body.config_src
        )
    except CloudflareAdapterUnavailable as exc:
        raise _wrap_unavailable(exc) from exc
    except CloudflareAdapterError as exc:
        raise _wrap_error(exc) from exc
    return asdict(created)


@router.delete(
    "/tunnels/{tunnel_id}",
    dependencies=[Depends(require_scope("cluster:admin"))],
)
def delete_tunnel(tunnel_id: str) -> dict[str, Any]:
    try:
        return get_cloudflare_adapter().delete_tunnel(tunnel_id=tunnel_id)
    except CloudflareAdapterUnavailable as exc:
        raise _wrap_unavailable(exc) from exc
    except CloudflareAdapterError as exc:
        raise _wrap_error(exc) from exc


@router.get(
    "/tunnels/{tunnel_id}/config",
    dependencies=[Depends(require_scope("cluster:read"))],
)
def get_tunnel_config(tunnel_id: str) -> dict[str, Any]:
    try:
        return get_cloudflare_adapter().get_tunnel_config(tunnel_id=tunnel_id)
    except CloudflareAdapterUnavailable as exc:
        raise _wrap_unavailable(exc) from exc
    except CloudflareAdapterError as exc:
        raise _wrap_error(exc) from exc


class PutTunnelConfigBody(BaseModel):
    ingress: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Cloudflare ingress rules — each item is a dict with "
            "'hostname' + 'service'. The adapter appends a catch-all "
            "'http_status:404' rule automatically."
        ),
    )


@router.put(
    "/tunnels/{tunnel_id}/config",
    dependencies=[Depends(require_scope("cluster:admin"))],
)
def put_tunnel_config(tunnel_id: str, body: PutTunnelConfigBody) -> dict[str, Any]:
    try:
        return get_cloudflare_adapter().put_tunnel_config(
            tunnel_id=tunnel_id, ingress=body.ingress
        )
    except CloudflareAdapterUnavailable as exc:
        raise _wrap_unavailable(exc) from exc
    except CloudflareAdapterError as exc:
        raise _wrap_error(exc) from exc


# ---------------------------------------------------------------------------
# Access apps
# ---------------------------------------------------------------------------


@router.get(
    "/access/apps",
    dependencies=[Depends(require_scope("cluster:read"))],
)
def list_access_apps() -> list[dict[str, Any]]:
    try:
        items = get_cloudflare_adapter().list_access_apps()
    except CloudflareAdapterUnavailable as exc:
        raise _wrap_unavailable(exc) from exc
    except CloudflareAdapterError as exc:
        raise _wrap_error(exc) from exc
    return [asdict(a) for a in items]


@router.put(
    "/access/apps",
    dependencies=[Depends(require_scope("cluster:admin"))],
)
def put_access_app(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        created = get_cloudflare_adapter().put_access_app(payload=payload)
    except CloudflareAdapterUnavailable as exc:
        raise _wrap_unavailable(exc) from exc
    except CloudflareAdapterError as exc:
        raise _wrap_error(exc) from exc
    return asdict(created)


# ---------------------------------------------------------------------------
# DNS
# ---------------------------------------------------------------------------


@router.get(
    "/dns/{zone_id}/records",
    dependencies=[Depends(require_scope("cluster:read"))],
)
def list_dns_records(zone_id: str, name: str | None = None) -> list[dict[str, Any]]:
    try:
        items = get_cloudflare_adapter().list_dns_records(zone_id=zone_id, name=name)
    except CloudflareAdapterUnavailable as exc:
        raise _wrap_unavailable(exc) from exc
    except CloudflareAdapterError as exc:
        raise _wrap_error(exc) from exc
    return [asdict(r) for r in items]


@router.put(
    "/dns/{zone_id}/records",
    dependencies=[Depends(require_scope("cluster:admin"))],
)
def put_dns_record(zone_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        created = get_cloudflare_adapter().put_dns_record(
            zone_id=zone_id, payload=payload
        )
    except CloudflareAdapterUnavailable as exc:
        raise _wrap_unavailable(exc) from exc
    except CloudflareAdapterError as exc:
        raise _wrap_error(exc) from exc
    return asdict(created)


@router.delete(
    "/dns/{zone_id}/records/{record_id}",
    dependencies=[Depends(require_scope("cluster:admin"))],
)
def delete_dns_record(zone_id: str, record_id: str) -> dict[str, Any]:
    try:
        return get_cloudflare_adapter().delete_dns_record(
            zone_id=zone_id, record_id=record_id
        )
    except CloudflareAdapterUnavailable as exc:
        raise _wrap_unavailable(exc) from exc
    except CloudflareAdapterError as exc:
        raise _wrap_error(exc) from exc


__all__ = ["router"]
