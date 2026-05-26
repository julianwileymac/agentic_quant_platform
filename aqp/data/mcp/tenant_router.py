"""Per-tenant MCP routing.

Phase 5 §8.1 (RESTRUCTURING_PLAN.md). Resolves an inbound MCP request
to the right tenant-scoped MCP server via the cells registry and the
tenant placement table.

The pre-Phase-5 path runs ONE shared ``aqp-data-mcp`` per cluster; the
Phase 5 path runs ONE MCP pool per cell with per-tenant cgroups
(``shared-std``) or one dedicated MCP pod per tenant
(``shared-prem`` / ``silo-reg``).

Topology:

    cell-<id>/
      mcp-pool/                       # shared-std: 1 deployment, N tenant cgroups
        aqp-data-mcp-pool-deployment
        aqp-codebase-mcp-pool-deployment
      mcp-tenant-<tenant_id>/         # shared-prem and silo-reg: per tenant
        aqp-data-mcp-<tenant_id>
        aqp-codebase-mcp-<tenant_id>

This module is the lookup helper used by:

- the in-process MCP bridge in ``aqp/agents/mcp_bridge.py`` (which
  currently calls the in-process tools directly; in Phase 5 it
  proxies to the per-tenant MCP server when ``settings.mcp_per_tenant``
  is enabled);
- the cell-router (Envoy) ext_authz callout that validates the
  ``aud`` claim on inbound MCP tokens (Rule 49) — the audience is
  the per-tenant MCP canonical URI returned by
  :func:`resolve_mcp_endpoint`.

The router is read-mostly. Cells / placements come from the cells
service the control plane already exposes; this module's job is to
translate ``(workspace_id, tenant_id, mcp_kind)`` to a concrete URL
+ audience.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Literal

logger = logging.getLogger(__name__)


# MCP server kinds shipped today. Phase 5 §8.1 deploys one of each
# per cell (shared-std) or per tenant (shared-prem / silo-reg).
McpKind = Literal["data", "codebase"]


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class McpEndpoint:
    """Resolved MCP endpoint for a (workspace, tenant, kind) triple.

    ``url`` is the in-cluster Service URL the agent's HTTP client hits.
    ``audience`` is the MCP audience claim per RFC 8707 (Rule 49) —
    every JWT the agent presents MUST carry this exact ``aud`` value.
    ``cell_id`` lets the caller stamp the audit ledger.
    """

    kind: McpKind
    url: str
    audience: str
    cell_id: str
    tenant_id: str
    isolation: Literal["shared", "dedicated"]


# ---------------------------------------------------------------------------
# Cache (sub-millisecond hot path)
# ---------------------------------------------------------------------------


_CACHE: dict[tuple[str, str, str], tuple[float, McpEndpoint]] = {}
_CACHE_LOCK = threading.RLock()
_CACHE_TTL_SECONDS = 30.0  # match the cells service refresh interval


def reset_cache() -> None:
    """Reset the per-process cache. Used by tests + the cells reload route."""
    with _CACHE_LOCK:
        _CACHE.clear()


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def resolve_mcp_endpoint(
    *,
    workspace_id: str,
    tenant_id: str,
    kind: McpKind,
    cell_id: str | None = None,
) -> McpEndpoint:
    """Return the MCP endpoint that serves ``(workspace_id, tenant_id, kind)``.

    Resolution order:
      1. If ``cell_id`` is provided, use it directly (the request
         already traversed ``aqp-edge`` and carries the ``X-AQP-Cell``
         header). This is the hot path.
      2. Otherwise, look up the tenant's pinning via the cells service
         (Phase 3 §6.2) — exact same registry the
         ``aqp-tenant-router`` consults.
      3. Pick the per-tenant MCP server when the cell tier is
         ``shared-prem`` or ``silo-reg``; pick the shared pool with a
         ``X-AQP-MCP-Tenant`` header (set by the caller, validated
         server-side by the cgroup gate) for ``shared-std``.

    Raises ``ValueError`` when no cell can serve the tenant.
    """
    cache_key = (workspace_id, tenant_id, kind)
    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
        if cached and (time.monotonic() - cached[0]) < _CACHE_TTL_SECONDS:
            return cached[1]

    cell = _resolve_cell(workspace_id=workspace_id, tenant_id=tenant_id, cell_id=cell_id)
    endpoint = _build_endpoint(cell=cell, tenant_id=tenant_id, kind=kind)
    with _CACHE_LOCK:
        _CACHE[cache_key] = (time.monotonic(), endpoint)
    return endpoint


def _resolve_cell(
    *,
    workspace_id: str,
    tenant_id: str,
    cell_id: str | None,
) -> dict[str, Any]:
    """Look up the cell for the tenant via the cells service.

    The cells service in ``aqp_control_plane`` (Phase 3 §6.2) already
    has the in-memory cell registry. We talk to it via its public
    Python API rather than the HTTP route to avoid the round-trip
    on the agent hot path.
    """
    if cell_id is not None:
        cell = _load_cell_by_id(cell_id)
        if cell is None:
            raise ValueError(f"unknown cell_id {cell_id!r}")
        return cell

    # Tenant pinning lookup. Today this defers to the cells service's
    # in-memory registry (Phase 3 §6.2). When the AQP runtime is
    # outside the control plane, we fall back to the topology YAML
    # directly so MCP routing keeps working in standalone deployments.
    pinned = _load_pinned_cell(tenant_id=tenant_id)
    if pinned is not None:
        return pinned

    # Fallback: the first active shared-std cell for the workspace.
    candidates = _load_active_cells_for_tier("shared-std")
    if not candidates:
        raise ValueError(
            f"no active cell available for workspace_id={workspace_id!r} "
            f"tenant_id={tenant_id!r}"
        )
    return candidates[0]


def _load_cell_by_id(cell_id: str) -> dict[str, Any] | None:
    try:
        from aqp_platform_core.topology import load_topology

        topo = load_topology()
        for cell in topo.cells:
            if cell.id == cell_id:
                return cell.model_dump()
    except Exception:  # noqa: BLE001
        logger.warning("tenant_router: topology load failed", exc_info=True)
    return None


def _load_pinned_cell(*, tenant_id: str) -> dict[str, Any] | None:
    try:
        from aqp_platform_core.topology import load_topology

        topo = load_topology()
        for cell in topo.cells:
            if tenant_id in (cell.pinned_tenants or []):
                return cell.model_dump()
    except Exception:  # noqa: BLE001
        logger.warning("tenant_router: topology load failed", exc_info=True)
    return None


def _load_active_cells_for_tier(tier: str) -> list[dict[str, Any]]:
    try:
        from aqp_platform_core.topology import load_topology

        topo = load_topology()
        return [
            cell.model_dump()
            for cell in topo.cells
            if cell.tier == tier and cell.state == "active"
        ]
    except Exception:  # noqa: BLE001
        logger.warning("tenant_router: topology load failed", exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Endpoint shape
# ---------------------------------------------------------------------------


def _build_endpoint(
    *,
    cell: dict[str, Any],
    tenant_id: str,
    kind: McpKind,
) -> McpEndpoint:
    """Translate ``(cell, tenant, kind)`` into the in-cluster MCP URL + audience."""
    cell_id = str(cell.get("id"))
    tier = str(cell.get("tier"))
    namespace = str(cell.get("k8s_namespace") or cell_id)

    if tier in {"shared-prem", "silo-reg"}:
        # Dedicated MCP pod per tenant. Service name carries the
        # tenant id so the cell-router routes directly without
        # cgroup gating.
        svc_name = f"aqp-{kind}-mcp-{tenant_id}"
        url = f"http://{svc_name}.{namespace}.svc.cluster.local:9100"
        audience = f"https://api.aqp.internal/mcp/{kind}/{tenant_id}/{cell_id}"
        isolation: Literal["dedicated"] = "dedicated"
    else:
        # shared-std: one MCP pool per cell, per-tenant cgroups
        # enforced by the pool. The agent attaches an X-AQP-MCP-Tenant
        # header that the pool's request handler validates.
        svc_name = f"aqp-{kind}-mcp-pool"
        url = f"http://{svc_name}.{namespace}.svc.cluster.local:9100"
        audience = f"https://api.aqp.internal/mcp/{kind}/{cell_id}"
        isolation = "shared"

    return McpEndpoint(
        kind=kind,
        url=url,
        audience=audience,
        cell_id=cell_id,
        tenant_id=tenant_id,
        isolation=isolation,
    )


# ---------------------------------------------------------------------------
# Outbound headers
# ---------------------------------------------------------------------------


def headers_for(endpoint: McpEndpoint, *, request_id: str | None = None) -> dict[str, str]:
    """Build the outbound HTTP header set for an MCP call.

    The caller still needs to attach ``Authorization: Bearer <jwt>``
    and (Phase 5 §8.2) ``X-Biscuit: <attenuated_biscuit>``; this
    helper covers the cell-routing / tenant-cgroup headers only.
    """
    out: dict[str, str] = {
        "X-AQP-Cell": endpoint.cell_id,
        "X-AQP-MCP-Tenant": endpoint.tenant_id,
        "X-AQP-MCP-Audience": endpoint.audience,
    }
    if request_id:
        out["X-Request-Id"] = request_id
    return out


__all__ = [
    "McpEndpoint",
    "McpKind",
    "headers_for",
    "reset_cache",
    "resolve_mcp_endpoint",
]
