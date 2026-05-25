"""Managed-service catalog — brokered to the control plane.

Reads call ``GET /manage/deployments`` on the CP and project the
response into the admin-facing :class:`ManagedService` shape.
Mutations are not implemented here yet — the route layer wires them
to ``execute_with_audit`` + ``ControlPlaneBroker.provision_tenant``
when the tenant-vending wizard is filed.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from aqp_admin.integrations import (
    AdminBrokerError,
    ControlPlaneBroker,
    get_brokers,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ManagedService:
    id: str
    kind: str
    org_id: str
    state: str
    namespace: str | None = None
    phase: str | None = None
    image: str | None = None
    replicas_desired: int = 0
    replicas_ready: int = 0


class ManagedServiceCatalog:
    """Brokered catalog of managed services across CP namespaces."""

    def __init__(self, *, control_plane: ControlPlaneBroker | None = None) -> None:
        self._cp = control_plane or get_brokers().control_plane

    async def list(self, *, namespace: str | None = None) -> list[ManagedService]:
        try:
            payload = await self._cp.list_deployments(namespace=namespace)
        except AdminBrokerError as exc:
            logger.warning("managed-service list broker call failed: %s", exc)
            return []
        rows = payload.get("data") or []
        out: list[ManagedService] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            out.append(
                ManagedService(
                    id=str(row.get("service_id") or ""),
                    kind=str(row.get("provider") or "unknown"),
                    org_id=str(row.get("namespace") or "").removeprefix("tenant-"),
                    state=str(row.get("phase") or "unknown"),
                    namespace=row.get("namespace"),
                    phase=row.get("phase"),
                    image=row.get("image"),
                    replicas_desired=int(row.get("replicas_desired") or 0),
                    replicas_ready=int(row.get("replicas_ready") or 0),
                )
            )
        return out

    async def provision(
        self,
        *,
        tenant_id: str,
        spec: dict[str, Any],
    ) -> dict[str, Any]:
        """Broker a tenant-namespace provision call to the CP."""
        return await self._cp.provision_tenant(tenant_id, spec)


__all__ = ["ManagedService", "ManagedServiceCatalog"]
