"""Tenancy invite + Entra-link helpers (stub).

Wires to AQP's tenancy_invites + entra_tenant_links tables through
`data.tenancy.*` MCP tools. AGENTS rule 44: never auto-create
Organization rows from raw Entra `tid` claims.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Invite:
    id: str
    org_id: str
    email: str
    status: str


class TenancyService:
    """Stub. Real impl proxies to `data.tenancy.list_invites` etc."""

    async def list_invites(self, org_id: str | None = None) -> list[Invite]:  # noqa: ARG002
        return []
