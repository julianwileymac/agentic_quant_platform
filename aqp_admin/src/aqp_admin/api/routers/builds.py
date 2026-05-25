"""``/admin/builds`` — brokered Kaniko in-cluster image builds.

Wraps the CP ``/manage/builds`` surface with audit-first writes so
the admin UI gets a single submit endpoint per build.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from aqp_admin.deps.audit import AuditContext, audit_context_dep
from aqp_admin.deps.identity import AdminUser, require_admin_scope
from aqp_admin.integrations import AdminBrokerError, get_brokers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/builds", tags=["builds"])


class BuildSubmitBody(BaseModel):
    """Mirrors :class:`aqp_cp.api.routers.builds.BuildSubmitBody`.

    Pydantic discriminator on the ``source.kind`` field happens
    server-side on the CP; we just pass the bag through.
    """

    image_ref: str = Field(..., min_length=1)
    source: dict[str, Any]
    namespace: str | None = None
    builder_sa: str | None = None
    image: str | None = None
    build_args: dict[str, str] = Field(default_factory=dict)
    extra_kaniko_args: list[str] = Field(default_factory=list)
    cache_enabled: bool = True
    backoff_limit: int | None = Field(default=None, ge=0, le=10)
    ttl_seconds_after_finished: int | None = Field(default=None, ge=60, le=86400)
    owner_uid: str | None = None
    owner_kind: str = "QuantAgent"
    owner_api_version: str = "aqp.io/v1"
    owner_name: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)


def _bearer_from_header(header_value: str | None) -> str | None:
    if not header_value or not header_value.lower().startswith("bearer "):
        return None
    return header_value.split(None, 1)[1].strip()


@router.post(
    "",
    summary="Submit a new in-cluster image build (audit-first).",
)
async def submit_build(
    body: BuildSubmitBody,
    user: AdminUser = Depends(require_admin_scope("manage:agents")),
    audit: AuditContext = Depends(audit_context_dep("admin.builds.submit")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    audit.target = body.image_ref
    audit.start(payload=body.model_dump())
    try:
        result = await get_brokers().control_plane.submit_build(body.model_dump())
    except AdminBrokerError as exc:
        audit.fail(str(exc))
        raise HTTPException(
            status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            detail={"error": exc.code, "error_description": str(exc)},
        ) from exc
    audit.succeed({"job_name": (result.get("data") or {}).get("job_name")})
    return result


@router.get(
    "/{job_name}",
    summary="Probe a previously-submitted Kaniko Job.",
)
async def build_status(
    job_name: str,
    namespace: str | None = None,
    user: AdminUser = Depends(require_admin_scope("read:infrastructure")),
) -> dict[str, Any]:
    try:
        return await get_brokers().control_plane.build_status(
            job_name, namespace=namespace
        )
    except AdminBrokerError as exc:
        raise HTTPException(
            status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            detail={"error": exc.code, "error_description": str(exc)},
        ) from exc


__all__ = ["router"]
