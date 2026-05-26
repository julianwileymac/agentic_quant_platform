"""``/manage/cells`` — cell-registry CRUD + state transitions.

Phase 3 §6.2 (RESTRUCTURING_PLAN.md). A "cell" is the deployment-layer
unit that composes with the application-layer ``TenancyStrategy``.

Routes:

- ``GET    /manage/cells``                       — list with filters
- ``GET    /manage/cells/{cell_id}``             — single cell
- ``POST   /manage/cells``                       — register a new cell
- ``PATCH  /manage/cells/{cell_id}/state``       — state transition
- ``DELETE /manage/cells/{cell_id}``             — decommission
- ``GET    /manage/cells/{cell_id}/tenants``     — list tenant pinnings
- ``POST   /manage/cells/{cell_id}/tenants``     — place a tenant
- ``POST   /manage/cells/{cell_id}/tenants/{tenant_id}/migrate``
                                                 — migrate to another cell
- ``POST   /manage/cells/reload``                — reseed from topology.yaml

Every mutation routes through :func:`execute_with_audit` so the
action lands in the ``workload_runs`` ledger BEFORE the registry
mutation commits (AGENTS rule 45).

Scopes:
- Reads (``GET`` everything): ``read:topology``.
- Mutations: ``manage:cells`` with step-up MFA gating in production
  per AGENTS rule 52.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, Header, Request

from aqp_platform_core.models.workloads import WorkloadAction
from aqp_platform_core.topology import Cell, CellState

from aqp_cp.auth.deps import AuthenticatedUser, require_scope
from aqp_cp.models import ResponseEnvelope
from aqp_cp.services import cells as cells_service
from aqp_cp.services.lifecycle import execute_with_audit

logger = logging.getLogger(__name__)

router = APIRouter(tags=["cells"], prefix="/cells")


# ---------------------------------------------------------------------------
# READ surface — every route requires read:topology (admin:cluster bypass).
# ---------------------------------------------------------------------------


@router.get(
    "",
    summary="List registered cells (with optional filters).",
    description=(
        "Returns every cell in the registry. Optional ``tier``, "
        "``region``, and ``state`` query parameters narrow the view. "
        "Required scope: ``read:topology``."
    ),
    response_model=ResponseEnvelope[list[dict[str, Any]]],
)
async def list_cells_route(
    tier: str | None = None,
    region: str | None = None,
    state: str | None = None,
    user: AuthenticatedUser = Depends(require_scope("read:topology")),
) -> ResponseEnvelope[list[dict[str, Any]]]:
    cells = cells_service.list_cells(tier=tier, region=region, state=state)
    return ResponseEnvelope(
        status="ok",
        data=[cell.model_dump() for cell in cells],
    )


@router.get(
    "/{cell_id}",
    summary="Single cell descriptor.",
    description=(
        "Returns the cell whose ``id`` matches ``cell_id``. 404 when "
        "unknown. Required scope: ``read:topology``."
    ),
    response_model=ResponseEnvelope[dict[str, Any]],
)
async def get_cell_route(
    cell_id: str,
    user: AuthenticatedUser = Depends(require_scope("read:topology")),
) -> ResponseEnvelope[dict[str, Any]]:
    cell = cells_service.get_cell(cell_id)
    return ResponseEnvelope(status="ok", data=cell.model_dump())


@router.get(
    "/{cell_id}/tenants",
    summary="List tenants pinned to this cell.",
    description=(
        "Returns the tenant-placement rows for the cell. Required "
        "scope: ``read:topology``."
    ),
    response_model=ResponseEnvelope[list[dict[str, Any]]],
)
async def list_cell_tenants_route(
    cell_id: str,
    user: AuthenticatedUser = Depends(require_scope("read:topology")),
) -> ResponseEnvelope[list[dict[str, Any]]]:
    placements = cells_service.list_cell_tenants(cell_id)
    return ResponseEnvelope(status="ok", data=placements)


# ---------------------------------------------------------------------------
# MUTATION surface — every route requires manage:cells + audit ledger.
# ---------------------------------------------------------------------------


@router.post(
    "",
    summary="Register a new cell.",
    description=(
        "Adds a new entry to the cell registry. The body MUST validate "
        "against the shared ``Cell`` Pydantic model "
        "(``aqp_platform_core.topology.Cell``). Per AGENTS rule 52 the "
        "UI should friction-gate this with a step-up MFA prompt. "
        "Required scope: ``manage:cells``."
    ),
    response_model=ResponseEnvelope[dict[str, Any]],
)
async def register_cell_route(
    cell: Cell,
    request: Request,
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    user: AuthenticatedUser = Depends(require_scope("manage:cells")),
) -> ResponseEnvelope[dict[str, Any]]:
    async def _do_register() -> Cell:
        return cells_service.register_cell(cell)

    _run, result = await execute_with_audit(
        action=WorkloadAction.REGISTER_CELL,
        target=cell.id,
        user=user,
        payload=cell.model_dump(mode="json"),
        fn=_do_register,
        request_id=x_request_id,
    )
    return ResponseEnvelope(status="ok", data=result.model_dump())


@router.patch(
    "/{cell_id}/state",
    summary="Transition a cell's state.",
    description=(
        "Valid transitions today (Phase 3 §6.2): "
        "``provisioning`` -> ``active`` -> ``draining`` -> "
        "``decommissioning`` -> ``archived``. ``suspended`` and "
        "``maintenance`` are entered from ``active`` for incident "
        "response. Required scope: ``manage:cells``."
    ),
    response_model=ResponseEnvelope[dict[str, Any]],
)
async def transition_cell_state_route(
    cell_id: str,
    request: Request,
    new_state: CellState = Body(..., embed=True, alias="state"),
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    user: AuthenticatedUser = Depends(require_scope("manage:cells")),
) -> ResponseEnvelope[dict[str, Any]]:
    async def _do_transition() -> Cell:
        return cells_service.transition_state(cell_id, new_state)

    _run, result = await execute_with_audit(
        action=WorkloadAction.UPDATE_CELL_STATE,
        target=cell_id,
        user=user,
        payload={"new_state": new_state},
        fn=_do_transition,
        request_id=x_request_id,
    )
    return ResponseEnvelope(status="ok", data=result.model_dump())


@router.delete(
    "/{cell_id}",
    summary="Decommission a cell.",
    description=(
        "Marks the cell as ``decommissioning``. The cell MUST be in "
        "``draining``/``suspended``/``maintenance`` AND have zero "
        "active tenant placements. Required scope: ``manage:cells``."
    ),
    response_model=ResponseEnvelope[dict[str, Any]],
)
async def decommission_cell_route(
    cell_id: str,
    request: Request,
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    user: AuthenticatedUser = Depends(require_scope("manage:cells")),
) -> ResponseEnvelope[dict[str, Any]]:
    async def _do_decommission() -> Cell:
        return cells_service.decommission_cell(cell_id)

    _run, result = await execute_with_audit(
        action=WorkloadAction.DECOMMISSION_CELL,
        target=cell_id,
        user=user,
        payload=None,
        fn=_do_decommission,
        request_id=x_request_id,
    )
    return ResponseEnvelope(status="ok", data=result.model_dump())


@router.post(
    "/{cell_id}/tenants",
    summary="Pin a tenant to a cell.",
    description=(
        "Adds the tenant to the cell's placement table with "
        "``placement=active``. Rejects when the cell isn't active or "
        "has a pinned-tenants whitelist that excludes the candidate. "
        "Required scope: ``manage:cells``."
    ),
    response_model=ResponseEnvelope[dict[str, Any]],
)
async def place_tenant_route(
    cell_id: str,
    request: Request,
    tenant_id: str = Body(..., embed=True),
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    user: AuthenticatedUser = Depends(require_scope("manage:cells")),
) -> ResponseEnvelope[dict[str, Any]]:
    async def _do_place() -> dict[str, Any]:
        return cells_service.place_tenant(cell_id, tenant_id)

    _run, result = await execute_with_audit(
        action=WorkloadAction.PLACE_TENANT_IN_CELL,
        target=f"{cell_id}:{tenant_id}",
        user=user,
        payload={"tenant_id": tenant_id, "cell_id": cell_id},
        fn=_do_place,
        request_id=x_request_id,
    )
    return ResponseEnvelope(status="ok", data=result)


@router.post(
    "/{cell_id}/tenants/{tenant_id}/migrate",
    summary="Migrate a tenant from this cell to another.",
    description=(
        "Marks the source placement ``migrated`` and creates a new "
        "``active`` placement at ``target_cell_id``. The actual data "
        "migration (Postgres dump-restore, MinIO sync) is Phase 6 "
        "§9.1. Required scope: ``manage:cells``."
    ),
    response_model=ResponseEnvelope[dict[str, Any]],
)
async def migrate_tenant_route(
    cell_id: str,
    tenant_id: str,
    request: Request,
    target_cell_id: str = Body(..., embed=True),
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    user: AuthenticatedUser = Depends(require_scope("manage:cells")),
) -> ResponseEnvelope[dict[str, Any]]:
    async def _do_migrate() -> dict[str, Any]:
        return cells_service.migrate_tenant(
            source_cell_id=cell_id,
            tenant_id=tenant_id,
            target_cell_id=target_cell_id,
        )

    _run, result = await execute_with_audit(
        action=WorkloadAction.MIGRATE_TENANT_TO_CELL,
        target=f"{tenant_id}:{cell_id}->{target_cell_id}",
        user=user,
        payload={
            "tenant_id": tenant_id,
            "source_cell_id": cell_id,
            "target_cell_id": target_cell_id,
        },
        fn=_do_migrate,
        request_id=x_request_id,
    )
    return ResponseEnvelope(status="ok", data=result)


@router.post(
    "/reload",
    summary="Reseed the cells registry from topology.yaml.",
    description=(
        "Resets the in-memory cells cache and re-hydrates from the "
        "topology YAML. Any unpersisted in-memory mutations are LOST. "
        "Operator-only; required scope: ``admin:cluster``."
    ),
    response_model=ResponseEnvelope[dict[str, Any]],
)
async def reload_cells_route(
    user: AuthenticatedUser = Depends(require_scope("admin:cluster")),
) -> ResponseEnvelope[dict[str, Any]]:
    cells_service.reset_cells_cache()
    cells = cells_service.list_cells()
    return ResponseEnvelope(
        status="ok",
        data={"reloaded": True, "cell_count": len(cells)},
    )
