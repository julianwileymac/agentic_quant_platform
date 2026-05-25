"""Organization service — brokered to monolith ``data.tenancy.*``.

Audit-first: the route layer writes the audit row BEFORE calling
:meth:`OrganizationService.create`. The service itself just brokers
the upstream call + maps errors to typed dataclasses.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from aqp_admin.integrations import (
    AdminBrokerError,
    ControlPlaneBroker,
    MonolithBroker,
    get_brokers,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OrganizationSummary:
    id: str
    name: str
    billing_status: str = "unknown"
    user_count: int = 0
    plan: str = "b2b"
    entra_tenant_id: str | None = None


class OrganizationService:
    """Brokered organization lookups + create flow."""

    def __init__(
        self,
        *,
        monolith: MonolithBroker | None = None,
        control_plane: ControlPlaneBroker | None = None,
    ) -> None:
        brokers = get_brokers() if monolith is None or control_plane is None else None
        self._monolith = monolith or (brokers.monolith if brokers else None)
        self._cp = control_plane or (brokers.control_plane if brokers else None)
        if self._monolith is None:
            raise RuntimeError("OrganizationService requires a MonolithBroker")

    async def list(self, *, bearer_passthrough: str | None = None) -> list[OrganizationSummary]:
        try:
            payload = await self._monolith.list_organizations(
                bearer_passthrough=bearer_passthrough
            )
        except AdminBrokerError as exc:
            logger.warning("list organizations broker call failed: %s", exc)
            return []
        rows = payload.get("data") or payload.get("organizations") or []
        return [_row_to_summary(r) for r in rows if isinstance(r, dict)]

    async def get(
        self,
        org_id: str,
        *,
        bearer_passthrough: str | None = None,
    ) -> OrganizationSummary | None:
        try:
            payload = await self._monolith.get_organization(
                org_id, bearer_passthrough=bearer_passthrough
            )
        except AdminBrokerError as exc:
            logger.warning("get organization %s broker call failed: %s", org_id, exc)
            return None
        body = payload.get("data") or payload
        if not isinstance(body, dict) or not body:
            return None
        return _row_to_summary(body)

    async def get_tenant_namespace_status(
        self, org_id: str
    ) -> dict[str, Any] | None:
        if self._cp is None:
            return None
        try:
            return await self._cp.tenant_status(org_id)
        except AdminBrokerError as exc:
            logger.warning("tenant_status %s broker call failed: %s", org_id, exc)
            return None


def _row_to_summary(row: dict[str, Any]) -> OrganizationSummary:
    return OrganizationSummary(
        id=str(row.get("id") or row.get("org_id") or ""),
        name=str(row.get("name") or row.get("display_name") or "<unknown>"),
        billing_status=str(row.get("billing_status") or "unknown"),
        user_count=int(row.get("user_count") or 0),
        plan=str(row.get("plan") or "b2b"),
        entra_tenant_id=row.get("entra_tenant_id"),
    )


__all__ = ["OrganizationService", "OrganizationSummary"]
