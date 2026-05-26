"""In-memory cell registry cache with periodic refresh.

Phase 3 §6.4 of [RESTRUCTURING_PLAN.md](../../../../RESTRUCTURING_PLAN.md).

The cache hits the control plane's ``/manage/cells`` route once at
boot and then on a refresh interval (default 30 s) to pull the live
cell list. Resolution is a pure-Python in-memory dict lookup on the
hot path; the refresh task runs in the background via asyncio.

Phase 5 §8.5 swaps the in-memory cache for Redis-backed shared
state so multiple ``aqp-tenant-router`` replicas share a single
cell view; until then we accept the brief inconsistency window
(at most ``refresh_interval_seconds``) right after a control-plane
mutation.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CellEntry:
    """One cached cell row.

    Lightweight mirror of ``aqp_platform_core.topology.Cell`` carrying
    only the fields the router needs on the resolution path. Mirroring
    keeps the router HTTP-only against the control plane — we do NOT
    take a runtime dep on ``aqp_platform_core`` for type safety.
    """

    id: str
    tier: str
    tenancy_strategy: str
    region: str
    availability_zone: str
    k8s_namespace: str
    state: str
    capacity_max_tenants: int
    pinned_tenants: tuple[str, ...]
    routes: dict[str, str]
    labels: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> CellEntry:
        return cls(
            id=str(data.get("id")),
            tier=str(data.get("tier")),
            tenancy_strategy=str(data.get("tenancy_strategy")),
            region=str(data.get("region")),
            availability_zone=str(data.get("availability_zone")),
            k8s_namespace=str(data.get("k8s_namespace")),
            state=str(data.get("state")),
            capacity_max_tenants=int(data.get("capacity_max_tenants", 1) or 1),
            pinned_tenants=tuple(data.get("pinned_tenants") or ()),
            routes=dict((data.get("routes") or {}).items()),
            labels=dict((data.get("labels") or {}).items()),
        )

    def is_active(self) -> bool:
        return self.state == "active"


class CellCache:
    """Thread-safe in-memory cell cache with background refresh."""

    def __init__(
        self,
        *,
        control_plane_url: str,
        refresh_interval_seconds: float = 30.0,
        request_timeout_seconds: float = 5.0,
        auth_header_provider: callable | None = None,  # type: ignore[type-arg]
    ) -> None:
        self._control_plane_url = control_plane_url.rstrip("/")
        self._refresh_interval = refresh_interval_seconds
        self._timeout = request_timeout_seconds
        self._auth_header_provider = auth_header_provider
        self._lock = threading.RLock()
        self._entries: dict[str, CellEntry] = {}
        # tenant_id -> cell_id (active pinning). When pinning is missing,
        # fall back to round-robin over active shared-std cells.
        self._tenant_pinnings: dict[str, str] = {}
        self._last_refresh: float = 0.0
        self._hydrated: bool = False
        self._refresh_task: asyncio.Task | None = None
        self._shutdown = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Hydrate once and start the background refresh task."""
        await self._refresh_once()
        self._refresh_task = asyncio.create_task(self._refresh_loop())

    async def stop(self) -> None:
        self._shutdown = True
        if self._refresh_task is not None:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass

    async def _refresh_loop(self) -> None:
        while not self._shutdown:
            try:
                await asyncio.sleep(self._refresh_interval)
            except asyncio.CancelledError:
                break
            if self._shutdown:
                break
            try:
                await self._refresh_once()
            except Exception:  # noqa: BLE001 - never break the refresh loop
                logger.exception("cell-cache refresh failed; will retry")

    async def _refresh_once(self) -> None:
        url = f"{self._control_plane_url}/manage/cells"
        headers: dict[str, str] = {}
        if self._auth_header_provider is not None:
            try:
                headers.update(self._auth_header_provider())
            except Exception:  # noqa: BLE001 - degrade rather than crash
                logger.warning("auth_header_provider raised; refreshing without auth")
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            body = resp.json()
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list):
            logger.warning(
                "cell-cache refresh: unexpected envelope shape (got %s)",
                type(data).__name__,
            )
            return
        entries: dict[str, CellEntry] = {}
        pinnings: dict[str, str] = {}
        for row in data:
            if not isinstance(row, dict):
                continue
            entry = CellEntry.from_api(row)
            entries[entry.id] = entry
            for tenant_id in entry.pinned_tenants:
                pinnings[tenant_id] = entry.id
        with self._lock:
            self._entries = entries
            self._tenant_pinnings = pinnings
            self._last_refresh = time.monotonic()
            self._hydrated = True
        logger.info(
            "cell-cache refresh: %d cells hydrated (%d pinned tenants)",
            len(entries),
            len(pinnings),
        )

    # ------------------------------------------------------------------
    # Read API (hot path — pure in-memory, no I/O)
    # ------------------------------------------------------------------

    def is_ready(self) -> bool:
        return self._hydrated and bool(self._entries)

    def get_cell(self, cell_id: str) -> CellEntry | None:
        with self._lock:
            return self._entries.get(cell_id)

    def get_pinned_cell_for_tenant(self, tenant_id: str) -> CellEntry | None:
        with self._lock:
            cell_id = self._tenant_pinnings.get(tenant_id)
            if cell_id is None:
                return None
            return self._entries.get(cell_id)

    def list_active_cells_for_tier(self, tier: str) -> list[CellEntry]:
        with self._lock:
            return [c for c in self._entries.values() if c.tier == tier and c.is_active()]

    def list_all(self) -> list[CellEntry]:
        with self._lock:
            return list(self._entries.values())


__all__ = ["CellCache", "CellEntry"]
