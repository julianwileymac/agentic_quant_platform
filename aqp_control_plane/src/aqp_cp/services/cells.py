"""Cells registry service — Phase 3 §6.2 (RESTRUCTURING_PLAN.md).

The cells registry is the deployment-layer source of truth that
composes with the application-layer ``TenancyStrategy``. The bootstrap
seed lives at ``aqp_platform/configs/deployment/topology.yaml::cells``
(parsed via :class:`aqp_platform_core.topology.DeploymentTopology`);
live updates flow through the ``/manage/cells/*`` routes which mutate
this in-memory service.

The store is intentionally in-memory + audit-log-backed today because
``aqp_control_plane`` does not yet have its own SQLAlchemy access
(Phase 6 §9.1 — per-cell Postgres adds that). The Alembic migration
``0082_cell_registry.py`` already creates the ``cells`` and
``cell_tenants`` tables in the main AQP Postgres; an in-cluster sidecar
or a future SQL backend wires the two together. Until then this
service:

1. Hydrates from ``topology.yaml`` on first read.
2. Applies in-memory mutations.
3. Emits ``workload_runs`` rows via the audit ledger.
4. Is reset by ``reset_cells_cache()`` (used by tests + the
   ``reload_topology`` admin endpoint).

When the DB backend lands, swap ``_REGISTRY`` for a SQLAlchemy
session-scoped query and keep the function signatures.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status

from aqp_platform_core.topology import (
    Cell,
    CellState,
    DeploymentTopology,
    load_topology,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# In-memory registry (Phase 3 §6.2 — replaced by DB in Phase 6 §9.1).
# ---------------------------------------------------------------------------


_REGISTRY: dict[str, Cell] | None = None
_TENANTS: dict[str, dict[str, dict[str, Any]]] | None = None  # cell_id -> tenant_id -> placement row
_LOCK = threading.RLock()


_TERMINAL_STATES: frozenset[str] = frozenset({"decommissioning", "archived"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hydrate_from_topology() -> None:
    """Seed ``_REGISTRY`` from the topology YAML the first time it is read.

    Safe to call multiple times — re-hydration is gated on
    ``_REGISTRY is None`` so live mutations are not lost.
    """
    global _REGISTRY, _TENANTS
    if _REGISTRY is not None:
        return
    try:
        topo: DeploymentTopology = load_topology()
        cells = list(topo.cells)
    except Exception as exc:  # noqa: BLE001 - defensive: never block reads
        logger.warning("cells service: topology load failed (%s); starting empty", exc)
        cells = []
    _REGISTRY = {cell.id: cell for cell in cells}
    _TENANTS = {
        cell.id: {
            tenant_id: {
                "tenant_id": tenant_id,
                "placement": "active",
                "placed_at": _now().isoformat(),
                "drained_at": None,
                "migrated_to_cell_id": None,
            }
            for tenant_id in cell.pinned_tenants
        }
        for cell in cells
    }


def reset_cells_cache() -> None:
    """Reset the in-memory registry. Tests + ``POST /manage/cells/reload``."""
    global _REGISTRY, _TENANTS
    with _LOCK:
        _REGISTRY = None
        _TENANTS = None


# ---------------------------------------------------------------------------
# Read API
# ---------------------------------------------------------------------------


def list_cells(
    *,
    tier: str | None = None,
    region: str | None = None,
    state: str | None = None,
) -> list[Cell]:
    """Return cells matching the optional filter triple."""
    with _LOCK:
        _hydrate_from_topology()
        assert _REGISTRY is not None  # nosec - guarded by _hydrate_from_topology
        cells = list(_REGISTRY.values())
    out: list[Cell] = []
    for cell in cells:
        if tier and cell.tier != tier:
            continue
        if region and cell.region != region:
            continue
        if state and cell.state != state:
            continue
        out.append(cell)
    return out


def get_cell(cell_id: str) -> Cell:
    with _LOCK:
        _hydrate_from_topology()
        assert _REGISTRY is not None  # nosec
        try:
            return _REGISTRY[cell_id]
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "cell_not_found", "cell_id": cell_id},
            )


def list_cell_tenants(cell_id: str) -> list[dict[str, Any]]:
    with _LOCK:
        _hydrate_from_topology()
        assert _TENANTS is not None  # nosec
        # Validate cell exists (raises 404 if not).
        get_cell(cell_id)
        return list(_TENANTS.get(cell_id, {}).values())


# ---------------------------------------------------------------------------
# Mutation API (every mutation must be wrapped by the route's
# ``execute_with_audit`` so the ``WorkloadRuntime`` audit ledger lands
# the action before this state changes — AGENTS rule 45).
# ---------------------------------------------------------------------------


def register_cell(cell: Cell) -> Cell:
    with _LOCK:
        _hydrate_from_topology()
        assert _REGISTRY is not None and _TENANTS is not None  # nosec
        if cell.id in _REGISTRY:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "cell_already_exists", "cell_id": cell.id},
            )
        # Uniqueness check on k8s_namespace (mirrors the DB UNIQUE index).
        for existing in _REGISTRY.values():
            if existing.k8s_namespace == cell.k8s_namespace:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": "namespace_already_used",
                        "k8s_namespace": cell.k8s_namespace,
                        "by_cell": existing.id,
                    },
                )
        _REGISTRY[cell.id] = cell
        _TENANTS[cell.id] = {
            tenant_id: {
                "tenant_id": tenant_id,
                "placement": "active",
                "placed_at": _now().isoformat(),
                "drained_at": None,
                "migrated_to_cell_id": None,
            }
            for tenant_id in cell.pinned_tenants
        }
    logger.info("cells: registered cell_id=%s tier=%s", cell.id, cell.tier)
    return cell


def transition_state(cell_id: str, new_state: CellState) -> Cell:
    """Apply a state transition. The matrix is intentionally permissive
    today and gets tightened in Phase 8 (cell drain primitives §11.1).
    """
    with _LOCK:
        cell = get_cell(cell_id)
        if cell.state in _TERMINAL_STATES and new_state != cell.state:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "cell_in_terminal_state",
                    "cell_id": cell_id,
                    "state": cell.state,
                },
            )
        updated = cell.model_copy(update={"state": new_state})
        _REGISTRY[cell_id] = updated  # type: ignore[index]
    logger.info(
        "cells: transition cell_id=%s %s -> %s", cell_id, cell.state, new_state
    )
    return updated


def place_tenant(cell_id: str, tenant_id: str) -> dict[str, Any]:
    with _LOCK:
        cell = get_cell(cell_id)
        if not cell.is_active():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "cell_not_active",
                    "cell_id": cell_id,
                    "state": cell.state,
                },
            )
        if cell.pinned_tenants and tenant_id not in cell.pinned_tenants:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "cell_has_pinned_tenants",
                    "cell_id": cell_id,
                    "pinned": cell.pinned_tenants,
                },
            )
        assert _TENANTS is not None  # nosec
        placement = {
            "tenant_id": tenant_id,
            "placement": "active",
            "placed_at": _now().isoformat(),
            "drained_at": None,
            "migrated_to_cell_id": None,
        }
        _TENANTS.setdefault(cell_id, {})[tenant_id] = placement
    logger.info("cells: placed tenant_id=%s in cell_id=%s", tenant_id, cell_id)
    return placement


def migrate_tenant(
    *, source_cell_id: str, tenant_id: str, target_cell_id: str
) -> dict[str, Any]:
    with _LOCK:
        source = get_cell(source_cell_id)
        target = get_cell(target_cell_id)
        assert _TENANTS is not None  # nosec
        if tenant_id not in _TENANTS.get(source_cell_id, {}):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "tenant_not_in_cell",
                    "tenant_id": tenant_id,
                    "cell_id": source_cell_id,
                },
            )
        if not target.is_active():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "target_cell_not_active",
                    "cell_id": target_cell_id,
                    "state": target.state,
                },
            )
        _TENANTS[source_cell_id][tenant_id].update(
            placement="migrated",
            drained_at=_now().isoformat(),
            migrated_to_cell_id=target_cell_id,
        )
        _TENANTS.setdefault(target_cell_id, {})[tenant_id] = {
            "tenant_id": tenant_id,
            "placement": "active",
            "placed_at": _now().isoformat(),
            "drained_at": None,
            "migrated_to_cell_id": None,
        }
        return dict(_TENANTS[target_cell_id][tenant_id])


def decommission_cell(cell_id: str) -> Cell:
    """Mark a cell decommissioned. Requires draining or empty tenant list."""
    with _LOCK:
        cell = get_cell(cell_id)
        assert _TENANTS is not None  # nosec
        active = [
            t
            for t in _TENANTS.get(cell_id, {}).values()
            if t.get("placement") == "active"
        ]
        if active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "cell_has_active_tenants",
                    "cell_id": cell_id,
                    "active_count": len(active),
                },
            )
        if cell.state not in {"draining", "suspended", "maintenance"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "cell_must_be_drained_first",
                    "cell_id": cell_id,
                    "state": cell.state,
                },
            )
        updated = cell.model_copy(update={"state": "decommissioning"})
        _REGISTRY[cell_id] = updated  # type: ignore[index]
    logger.info("cells: decommissioning cell_id=%s", cell_id)
    return updated
