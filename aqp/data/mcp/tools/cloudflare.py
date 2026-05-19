"""DataMCP tools wrapping the Cloudflare edge surface (Phase D).

Agents reach Cloudflare tunnel / DNS / Access app inventory + lifecycle
through these tools (AGENTS rule 22). All calls dispatch through
:func:`aqp.cloudflare.get_cloudflare_adapter` so the same SDK client
backs the REST routes and the in-process MCP catalog.

The Management Engine subagent rule
(``.cursor/rules/aqp-management-engine.mdc``) forbids logging tunnel
secrets, Access app client_secrets, or DNS API tokens. These tools
return only the public metadata Cloudflare's API exposes for read ops;
write ops accept payload dicts but the adapter never persists secret
material.
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from pydantic import BaseModel, Field

from aqp.cloudflare import (
    CloudflareAdapterError,
    CloudflareAdapterUnavailable,
    get_cloudflare_adapter,
)
from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# data.cloudflare.health
# ---------------------------------------------------------------------------


class HealthInput(BaseModel):
    pass


@register_data_mcp_tool
class CloudflareHealthTool(DataMCPTool):
    name = "data.cloudflare.health"
    description = (
        "Probe the Cloudflare API client (token verify). Returns "
        "{status, account_id, token_id, token_status}."
    )
    args_schema = HealthInput
    category = "cloudflare"
    tags = ("cloudflare", "health")
    required_scopes = ("cluster:read",)

    def run(self, *, ctx: MCPToolContext) -> MCPToolResult:
        return MCPToolResult(
            ok=True, data=get_cloudflare_adapter().health(), summary="cloudflare health"
        )


# ---------------------------------------------------------------------------
# data.cloudflare.list_tunnels
# ---------------------------------------------------------------------------


class ListTunnelsInput(BaseModel):
    name: str | None = Field(default=None, description="Optional name filter.")


@register_data_mcp_tool
class ListTunnelsTool(DataMCPTool):
    name = "data.cloudflare.list_tunnels"
    description = (
        "List Cloudflare Zero Trust tunnels for the active account. "
        "Returns compact descriptors (id, name, status, connections)."
    )
    args_schema = ListTunnelsInput
    category = "cloudflare"
    tags = ("cloudflare", "tunnels", "browse")
    required_scopes = ("cluster:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        name: str | None = None,
    ) -> MCPToolResult:
        try:
            items = get_cloudflare_adapter().list_tunnels(name=name)
        except CloudflareAdapterUnavailable as exc:
            return MCPToolResult(
                ok=False, error=f"adapter unavailable: {exc}", summary="cf unavailable"
            )
        except CloudflareAdapterError as exc:
            return MCPToolResult(ok=False, error=str(exc), summary="cf list failed")
        data = [asdict(t) for t in items]
        return MCPToolResult(
            ok=True,
            data={"tunnels": data},
            rows_returned=len(data),
            summary=f"listed {len(data)} cloudflare tunnels",
        )


# ---------------------------------------------------------------------------
# data.cloudflare.create_tunnel
# ---------------------------------------------------------------------------


class CreateTunnelInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    config_src: str = Field(default="cloudflare")


@register_data_mcp_tool
class CreateTunnelTool(DataMCPTool):
    name = "data.cloudflare.create_tunnel"
    description = (
        "Create a new Cloudflare Zero Trust tunnel. Mutating. Returns the "
        "new tunnel's id + status."
    )
    args_schema = CreateTunnelInput
    category = "cloudflare"
    tags = ("cloudflare", "tunnels", "write")
    required_scopes = ("cluster:admin",)
    mutates = True

    def run(
        self,
        *,
        ctx: MCPToolContext,
        name: str,
        config_src: str = "cloudflare",
    ) -> MCPToolResult:
        try:
            created = get_cloudflare_adapter().create_tunnel(
                name=name, config_src=config_src
            )
        except CloudflareAdapterUnavailable as exc:
            return MCPToolResult(
                ok=False, error=str(exc), summary="cf create_tunnel unavailable"
            )
        except CloudflareAdapterError as exc:
            return MCPToolResult(
                ok=False, error=str(exc), summary="cf create_tunnel failed"
            )
        return MCPToolResult(
            ok=True, data=asdict(created), summary=f"created tunnel {name}"
        )


# ---------------------------------------------------------------------------
# data.cloudflare.put_tunnel_config
# ---------------------------------------------------------------------------


class PutTunnelConfigInput(BaseModel):
    tunnel_id: str
    ingress: list[dict[str, Any]] = Field(default_factory=list)


@register_data_mcp_tool
class PutTunnelConfigTool(DataMCPTool):
    name = "data.cloudflare.put_tunnel_config"
    description = (
        "Replace the ingress rules of a Cloudflare tunnel. Mutating. The "
        "adapter appends a catch-all 'http_status:404' rule."
    )
    args_schema = PutTunnelConfigInput
    category = "cloudflare"
    tags = ("cloudflare", "tunnels", "config")
    required_scopes = ("cluster:admin",)
    mutates = True

    def run(
        self,
        *,
        ctx: MCPToolContext,
        tunnel_id: str,
        ingress: list[dict[str, Any]] | None = None,
    ) -> MCPToolResult:
        try:
            res = get_cloudflare_adapter().put_tunnel_config(
                tunnel_id=tunnel_id, ingress=list(ingress or [])
            )
        except CloudflareAdapterUnavailable as exc:
            return MCPToolResult(
                ok=False, error=str(exc), summary="cf put_tunnel_config unavailable"
            )
        except CloudflareAdapterError as exc:
            return MCPToolResult(
                ok=False, error=str(exc), summary="cf put_tunnel_config failed"
            )
        return MCPToolResult(
            ok=True, data=res, summary=f"updated tunnel {tunnel_id} ingress"
        )


# ---------------------------------------------------------------------------
# data.cloudflare.list_access_apps
# ---------------------------------------------------------------------------


class ListAccessAppsInput(BaseModel):
    pass


@register_data_mcp_tool
class ListAccessAppsTool(DataMCPTool):
    name = "data.cloudflare.list_access_apps"
    description = "List Cloudflare Access applications (browser-tested apps)."
    args_schema = ListAccessAppsInput
    category = "cloudflare"
    tags = ("cloudflare", "access", "browse")
    required_scopes = ("cluster:read",)

    def run(self, *, ctx: MCPToolContext) -> MCPToolResult:
        try:
            items = get_cloudflare_adapter().list_access_apps()
        except CloudflareAdapterUnavailable as exc:
            return MCPToolResult(ok=False, error=str(exc), summary="cf access unavailable")
        except CloudflareAdapterError as exc:
            return MCPToolResult(ok=False, error=str(exc), summary="cf access failed")
        data = [asdict(a) for a in items]
        return MCPToolResult(
            ok=True,
            data={"apps": data},
            rows_returned=len(data),
            summary=f"listed {len(data)} access apps",
        )


# ---------------------------------------------------------------------------
# data.cloudflare.put_access_app
# ---------------------------------------------------------------------------


class PutAccessAppInput(BaseModel):
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Cloudflare Access application payload (name, domain, type, "
            "session_duration, policies, ...). Include 'id' to update."
        ),
    )


@register_data_mcp_tool
class PutAccessAppTool(DataMCPTool):
    name = "data.cloudflare.put_access_app"
    description = (
        "Create or update a Cloudflare Access application. Mutating. "
        "Returns the resulting app's id + domain."
    )
    args_schema = PutAccessAppInput
    category = "cloudflare"
    tags = ("cloudflare", "access", "write")
    required_scopes = ("cluster:admin",)
    mutates = True

    def run(
        self,
        *,
        ctx: MCPToolContext,
        payload: dict[str, Any] | None = None,
    ) -> MCPToolResult:
        try:
            created = get_cloudflare_adapter().put_access_app(
                payload=dict(payload or {})
            )
        except CloudflareAdapterUnavailable as exc:
            return MCPToolResult(ok=False, error=str(exc), summary="cf access unavailable")
        except CloudflareAdapterError as exc:
            return MCPToolResult(ok=False, error=str(exc), summary="cf put_access_app failed")
        return MCPToolResult(ok=True, data=asdict(created), summary="put access app")


# ---------------------------------------------------------------------------
# data.cloudflare.put_dns_record
# ---------------------------------------------------------------------------


class PutDnsRecordInput(BaseModel):
    zone_id: str = Field(..., min_length=1)
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "DNS record payload (name, type, content, ttl, proxied). "
            "Include 'id' to update an existing record."
        ),
    )


@register_data_mcp_tool
class PutDnsRecordTool(DataMCPTool):
    name = "data.cloudflare.put_dns_record"
    description = (
        "Create or update a Cloudflare DNS record. Mutating. Returns "
        "the resulting record's id + content."
    )
    args_schema = PutDnsRecordInput
    category = "cloudflare"
    tags = ("cloudflare", "dns", "write")
    required_scopes = ("cluster:admin",)
    mutates = True

    def run(
        self,
        *,
        ctx: MCPToolContext,
        zone_id: str,
        payload: dict[str, Any] | None = None,
    ) -> MCPToolResult:
        try:
            created = get_cloudflare_adapter().put_dns_record(
                zone_id=zone_id, payload=dict(payload or {})
            )
        except CloudflareAdapterUnavailable as exc:
            return MCPToolResult(ok=False, error=str(exc), summary="cf dns unavailable")
        except CloudflareAdapterError as exc:
            return MCPToolResult(ok=False, error=str(exc), summary="cf put_dns_record failed")
        return MCPToolResult(ok=True, data=asdict(created), summary="put dns record")


__all__: list[str] = []
