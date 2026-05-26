# ruff: noqa: B008, ARG001
"""``/admin/lineage`` — bipartite lineage graph explorer.

Wraps the rule-48 bipartite lineage graph (dataset_vertex ↔
transform_vertex ↔ edge) by brokering to the monolith's
``data.lineage.*`` DataMCP tools. Read-only; no mutations.
"""
from __future__ import annotations

from typing import Any, NoReturn
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from aqp_admin.deps.identity import AdminUser, require_admin_scope
from aqp_admin.integrations import AdminBrokerError, get_brokers

router = APIRouter(prefix="/admin/lineage", tags=["lineage"])


def _bearer_from_header(header_value: str | None) -> str | None:
    if not header_value or not header_value.lower().startswith("bearer "):
        return None
    return header_value.split(None, 1)[1].strip()


def _raise_broker_error(exc: AdminBrokerError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
        detail={"error": exc.code, "error_description": str(exc)},
    ) from exc


@router.get("/datasets", summary="List dataset vertices.")
async def list_dataset_vertices(
    namespace: str | None = None,
    medallion_layer: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    user: AdminUser = Depends(require_admin_scope("read:infrastructure")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """List dataset vertices in the bipartite graph (paginated).

    Filters by Iceberg namespace + medallion layer. The vertex
    response includes ``urn``, ``namespace``, ``table``,
    ``medallion_layer``, ``current_snapshot_id``,
    ``manifest_list_location`` (Iceberg-resident only).
    """
    try:
        return await get_brokers().monolith.list_lineage_datasets(
            namespace=namespace,
            medallion_layer=medallion_layer,
            limit=limit,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


@router.get("/datasets/{urn:path}", summary="Describe one dataset vertex.")
async def describe_dataset(
    urn: str,
    user: AdminUser = Depends(require_admin_scope("read:infrastructure")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """Read one dataset vertex including its content-address.

    The URN may be URL-encoded; we ``unquote`` so the caller can
    pass an Iceberg URN like
    ``aqp_silver_market_data%2Fdaily_bars`` straight through.
    """
    try:
        return await get_brokers().monolith.describe_lineage_dataset(
            unquote(urn),
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


@router.get(
    "/datasets/{urn:path}/ancestry",
    summary="Walk the ancestry graph for a dataset.",
)
async def dataset_ancestry(
    urn: str,
    depth: int = Query(default=3, ge=1, le=10),
    user: AdminUser = Depends(require_admin_scope("read:infrastructure")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """Return the upstream ancestry subgraph for the given dataset.

    Drives the lineage explorer's Sankey diagram. Walks ``depth``
    transform-vertex hops; the response is a JSON-LD slice with
    ``vertices`` + ``edges``.
    """
    try:
        return await get_brokers().monolith.lineage_ancestry(
            unquote(urn),
            depth=depth,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


@router.get(
    "/datasets/{urn:path}/impact",
    summary="Walk the downstream impact graph for a dataset.",
)
async def dataset_impact(
    urn: str,
    depth: int = Query(default=3, ge=1, le=10),
    user: AdminUser = Depends(require_admin_scope("read:infrastructure")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """Return the downstream impact subgraph for the given dataset.

    Used when an operator asks "what breaks if I deprecate this
    table?". Mirror of ancestry but in the opposite direction.
    """
    try:
        return await get_brokers().monolith.lineage_impact(
            unquote(urn),
            depth=depth,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


@router.get(
    "/transforms",
    summary="List transform vertices.",
)
async def list_transforms(
    transform_kind: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    user: AdminUser = Depends(require_admin_scope("read:infrastructure")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """List transform vertices.

    ``transform_kind`` is one of the documented kinds:
    ``mcp_tool``, ``celery_task``, ``airflow_dag``, ``manual_sql``,
    ``discovery.promoted``.
    """
    try:
        return await get_brokers().monolith.list_lineage_transforms(
            transform_kind=transform_kind,
            limit=limit,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


@router.get(
    "/transforms/{transform_id}",
    summary="Describe one transform vertex.",
)
async def describe_transform(
    transform_id: str,
    user: AdminUser = Depends(require_admin_scope("read:infrastructure")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    try:
        return await get_brokers().monolith.describe_lineage_transform(
            transform_id,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


__all__ = ["router"]
