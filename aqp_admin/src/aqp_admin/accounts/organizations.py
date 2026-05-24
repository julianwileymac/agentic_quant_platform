"""Organization service stub. Real impl brokers to `data.tenancy.*` MCP."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OrganizationSummary:
    id: str
    name: str
    billing_status: str
    user_count: int


class OrganizationService:
    """Stub. Real impl wires to the topology + tenancy MCP catalog."""

    async def list(self) -> list[OrganizationSummary]:
        return []

    async def get(self, org_id: str) -> OrganizationSummary | None:  # noqa: ARG002
        return None
