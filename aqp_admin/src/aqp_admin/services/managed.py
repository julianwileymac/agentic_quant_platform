"""Managed-service catalog facade.

Real impl brokers provisioning/suspend/quota changes through the control
plane's /manage/deployments routes (AQP rule 45 - InfrastructureProvider).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ManagedService:
    id: str
    kind: str
    org_id: str
    state: str


class ManagedServiceCatalog:
    """Stub. Real impl proxies through aqp_control_plane."""

    async def list(self) -> list[ManagedService]:
        return []

    async def provision(self, org_id: str, kind: str) -> ManagedService:
        return ManagedService(id="stub", kind=kind, org_id=org_id, state="pending")
