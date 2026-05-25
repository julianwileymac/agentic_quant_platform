"""Tenancy invite + Entra-link helpers — brokered to the monolith.

Tenancy mutations route through the monolith's ``/tenancy/*`` REST
surface; reads route through the matching ``data.tenancy.*`` MCP
tools so the admin BFF respects the same access path as the
operator UI.

AGENTS rule 44 still applies: never auto-create ``Organization``
rows from raw Entra ``tid`` claims — pending links require a human
super-admin to promote via the wizard. The admin BFF surfaces the
list of pending links; the route handler is responsible for the
audit row.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from aqp_admin.integrations import (
    AdminBrokerError,
    MonolithBroker,
    get_brokers,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Invite:
    id: str
    org_id: str
    email: str
    role: str
    status: str
    expires_at: str | None = None


@dataclass(frozen=True, slots=True)
class EntraTenantLink:
    id: str
    org_id: str
    entra_tenant_id: str
    status: str
    created_at: str | None = None


class TenancyService:
    """Brokered tenancy invite + Entra-link reads + writes."""

    def __init__(self, *, monolith: MonolithBroker | None = None) -> None:
        self._monolith = monolith or get_brokers().monolith

    async def list_invites(
        self,
        org_id: str | None = None,
        *,
        bearer_passthrough: str | None = None,
    ) -> list[Invite]:
        try:
            payload = await self._monolith.list_invites(
                org_id, bearer_passthrough=bearer_passthrough
            )
        except AdminBrokerError as exc:
            logger.warning("list invites broker failed: %s", exc)
            return []
        rows = payload.get("data") or payload.get("invites") or []
        return [_row_to_invite(r) for r in rows if isinstance(r, dict)]

    async def create_invite(
        self,
        *,
        org_id: str,
        email: str,
        role: str,
        bearer_passthrough: str | None = None,
    ) -> Invite | None:
        try:
            payload = await self._monolith.create_invite(
                org_id=org_id,
                email=email,
                role=role,
                bearer_passthrough=bearer_passthrough,
            )
        except AdminBrokerError as exc:
            logger.warning("create invite broker failed: %s", exc)
            return None
        body = payload.get("data") or payload
        if not isinstance(body, dict):
            return None
        return _row_to_invite(body)

    async def list_entra_links(
        self,
        *,
        bearer_passthrough: str | None = None,
    ) -> list[EntraTenantLink]:
        try:
            payload = await self._monolith.list_entra_links(
                bearer_passthrough=bearer_passthrough
            )
        except AdminBrokerError as exc:
            logger.warning("list entra links broker failed: %s", exc)
            return []
        rows = payload.get("data") or payload.get("links") or []
        return [_row_to_link(r) for r in rows if isinstance(r, dict)]

    async def link_org_to_entra_tenant(
        self,
        *,
        org_id: str,
        tenant_id: str,
        bearer_passthrough: str | None = None,
    ) -> EntraTenantLink | None:
        try:
            payload = await self._monolith.link_org_to_entra_tenant(
                org_id=org_id,
                tenant_id=tenant_id,
                bearer_passthrough=bearer_passthrough,
            )
        except AdminBrokerError as exc:
            logger.warning("link entra tenant broker failed: %s", exc)
            return None
        body = payload.get("data") or payload
        if not isinstance(body, dict):
            return None
        return _row_to_link(body)


def _row_to_invite(row: dict[str, Any]) -> Invite:
    return Invite(
        id=str(row.get("id") or row.get("invite_id") or ""),
        org_id=str(row.get("org_id") or ""),
        email=str(row.get("email") or ""),
        role=str(row.get("role") or "viewer"),
        status=str(row.get("status") or "pending"),
        expires_at=row.get("expires_at"),
    )


def _row_to_link(row: dict[str, Any]) -> EntraTenantLink:
    return EntraTenantLink(
        id=str(row.get("id") or row.get("link_id") or ""),
        org_id=str(row.get("org_id") or ""),
        entra_tenant_id=str(row.get("entra_tenant_id") or row.get("tenant_id") or ""),
        status=str(row.get("status") or "pending"),
        created_at=row.get("created_at"),
    )


__all__ = ["EntraTenantLink", "Invite", "TenancyService"]
