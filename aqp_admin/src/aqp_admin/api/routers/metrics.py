"""``/admin/metrics`` — identity-aware PromQL proxy passthrough.

The CP already exposes the tenant-scoped Prometheus endpoint at
``/manage/observability/prometheus/query/tenant``; this router is a
narrow brokered passthrough so the admin UI hits a single host.

The bearer header is forwarded verbatim — the CP enforces the
identity-aware label injection.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from aqp_admin.deps.identity import AdminUser, require_admin_scope
from aqp_admin.integrations import AdminBrokerError, get_brokers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/metrics", tags=["metrics"])


class PromQueryBody(BaseModel):
    expression: str = Field(..., min_length=1)
    time: float | None = None


def _bearer_from_header(header_value: str | None) -> str:
    if not header_value or not header_value.lower().startswith("bearer "):
        return ""
    return header_value.split(None, 1)[1].strip()


@router.post(
    "/prometheus/query",
    summary="Tenant-scoped PromQL instant query (brokered to CP).",
)
async def prometheus_query(
    body: PromQueryBody,
    user: AdminUser = Depends(require_admin_scope("read:observability")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, object]:
    bearer = _bearer_from_header(authorization)
    try:
        return await get_brokers().control_plane.prometheus_query_tenant(
            expression=body.expression,
            time=body.time,
            bearer_passthrough=bearer or None,
        )
    except AdminBrokerError as exc:
        raise HTTPException(
            status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            detail={"error": exc.code, "error_description": str(exc)},
        ) from exc


__all__ = ["router"]
