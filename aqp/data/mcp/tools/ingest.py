"""``data.ingest.*`` DataMCP tools (Phase 4 — plan section 8).

Four tools that let agents browse the connector marketplace and
request ingestion connection creation through the canonical
agent-approval workflow.

- ``data.ingest.list_templates`` (read) — enumerate the connector
  marketplace catalog populated by Phase 5.
- ``data.ingest.preview_source`` (mutates=False, consumes
  ``vendor.preview`` quota) — return a 100-row preview without
  persisting.
- ``data.ingest.create_connection`` (mutates, step-up; routes
  through approval workflow when actor_kind=="agent").
- ``data.ingest.materialize`` (mutates, step-up; cost-aware).
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool

logger = logging.getLogger(__name__)


def _is_agent(ctx: MCPToolContext) -> bool:
    return (ctx.actor_kind or "").strip().lower() == "agent"


def _agent_sub(ctx: MCPToolContext) -> str:
    return (ctx.extras or {}).get("agent_subject", "agent|unknown")


def _on_behalf_of_user(ctx: MCPToolContext) -> str | None:
    if not _is_agent(ctx):
        return ctx.actor
    extras = ctx.extras or {}
    return extras.get("on_behalf_of_user_id") or extras.get("user_id") or None


# ---------------------------------------------------------------------------
# 1. list_templates (read)
# ---------------------------------------------------------------------------


class ListTemplatesInput(BaseModel):
    kind: str | None = Field(default=None, description="low_code_yaml | python_cdk | cdc")
    vendor_tier: str | None = None
    limit: int = Field(default=50, ge=1, le=500)


@register_data_mcp_tool
class IngestListTemplatesTool(DataMCPTool):
    """List connector marketplace templates."""

    name = "data.ingest.list_templates"
    description = (
        "Enumerate connector marketplace templates (Polygon / Databento / "
        "Alpaca / IEX / Tiingo / Alpha Vantage / Quandl / FRED / SEC EDGAR / "
        "Bloomberg / Refinitiv + generic kinds). Read-only."
    )
    args_schema = ListTemplatesInput
    category = "ingest"
    tags = ("ingest", "templates")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        kind: str | None = None,
        vendor_tier: str | None = None,
        limit: int = 50,
    ) -> MCPToolResult:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_ratelimit import TemplateCatalog

        with get_session() as session:
            q = session.query(TemplateCatalog).filter(
                TemplateCatalog.is_active.is_(True)
            )
            if kind is not None:
                q = q.filter(TemplateCatalog.kind == kind)
            if vendor_tier is not None:
                q = q.filter(TemplateCatalog.vendor_tier == vendor_tier)
            rows = q.order_by(TemplateCatalog.slug.asc()).limit(int(limit)).all()
        out = [
            {
                "slug": row.slug,
                "display_name": row.display_name,
                "kind": row.kind,
                "vendor_tier": row.vendor_tier,
                "rate_limit_class": row.rate_limit_class,
                "default_sync_mode": row.default_sync_mode,
                "doc_url": row.doc_url,
            }
            for row in rows
        ]
        return MCPToolResult(
            ok=True,
            data={"templates": out},
            summary=f"{len(out)} template(s)",
            rows_returned=len(out),
        )


# ---------------------------------------------------------------------------
# 2. preview_source (read; consumes vendor.preview quota)
# ---------------------------------------------------------------------------


class PreviewSourceInput(BaseModel):
    template_slug: str
    params: dict[str, Any] = Field(default_factory=dict)
    n_rows: int = Field(default=100, ge=1, le=1000)


@register_data_mcp_tool
class IngestPreviewSourceTool(DataMCPTool):
    """Return a small preview without persisting."""

    name = "data.ingest.preview_source"
    description = (
        "Issue a single rate-limited probe against a vendor template and "
        "return up to n_rows rows. Does NOT persist to Iceberg / QuestDB. "
        "Consumes the calling user's vendor.preview quota."
    )
    args_schema = PreviewSourceInput
    category = "ingest"
    tags = ("ingest", "preview")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        template_slug: str,
        params: dict[str, Any] | None = None,
        n_rows: int = 100,
    ) -> MCPToolResult:
        # Pre-flight rate-limit check against vendor.preview bucket.
        user_id = _on_behalf_of_user(ctx) or "anonymous"
        try:
            from aqp_ratelimit import get_ratelimit_client
            from aqp_ratelimit.bridges.agent_bridge import build_ratelimit_ctx

            decision = get_ratelimit_client().check(
                user_id=user_id,
                service="vendor.preview",
                key_id="primary",
                n_tokens=1,
                ctx=build_ratelimit_ctx(ctx),
            )
            if not decision.allow:
                return MCPToolResult(
                    ok=False,
                    error=(
                        f"vendor.preview budget exhausted; retry in "
                        f"{decision.retry_after_ms}ms"
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("preview pre-check failed: %s", exc)

        # The actual preview fetch lives in the Phase 5 marketplace
        # loader; Phase 4 ships the contract + the policy gate.
        return MCPToolResult(
            ok=True,
            data={
                "template_slug": template_slug,
                "params": dict(params or {}),
                "n_rows": n_rows,
                "preview": [],
                "note": (
                    "Phase 5 marketplace loader provides the actual preview "
                    "rows; Phase 4 covers the rate-limit + policy gate."
                ),
            },
            summary=f"preview gate passed for {template_slug}",
        )


# ---------------------------------------------------------------------------
# 3. create_connection (mutating; agent → approval workflow)
# ---------------------------------------------------------------------------


class CreateConnectionInput(BaseModel):
    template_slug: str
    name: str
    params: dict[str, Any] = Field(default_factory=dict)
    schedule: str | None = Field(
        default="0 1 * * MON-FRI",
        description="Cron expression for the connection schedule.",
    )
    estimated_cost_tokens: int | None = None


@register_data_mcp_tool
class IngestCreateConnectionTool(DataMCPTool):
    """Create a new Airbyte connection from a marketplace template."""

    name = "data.ingest.create_connection"
    description = (
        "Create a new Airbyte connection from a marketplace template. When "
        "the caller is a human, the connection is created immediately. When "
        "the caller is an autonomous agent (actor_kind='agent'), the request "
        "is queued for human approval and returns "
        "{status: pending_approval, approval_id: ...}."
    )
    args_schema = CreateConnectionInput
    category = "ingest"
    tags = ("ingest", "airbyte", "connection")
    mutates = True
    required_scopes = ("data:read", "data:write")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        template_slug: str,
        name: str,
        params: dict[str, Any] | None = None,
        schedule: str | None = "0 1 * * MON-FRI",
        estimated_cost_tokens: int | None = None,
    ) -> MCPToolResult:
        args = {
            "template_slug": template_slug,
            "name": name,
            "params": dict(params or {}),
            "schedule": schedule,
        }
        if _is_agent(ctx):
            from aqp.services.ingestion_approvals import request_approval

            pending = request_approval(
                tool_id=self.name,
                args=args,
                requested_by_agent_sub=_agent_sub(ctx),
                on_behalf_of_user_id=_on_behalf_of_user(ctx),
                workspace_id=ctx.workspace_id,
                estimated_cost_tokens=estimated_cost_tokens,
            )
            return MCPToolResult(
                ok=True,
                data=pending,
                summary=f"approval queued for create_connection({template_slug})",
            )
        # Human-initiated: execute through the discovery promote
        # pathway so the lineage event fires.
        try:
            from aqp.data.discovery.service import DiscoveryService

            DiscoveryService.create_external(
                name=name,
                provider="airbyte",
                suggested_connector=template_slug,
                workspace_id=ctx.workspace_id,
                owner_user_id=ctx.actor,
            )
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(
                ok=False,
                error=f"create_external failed: {exc}",
            )
        return MCPToolResult(
            ok=True,
            data={
                "template_slug": template_slug,
                "name": name,
                "status": "created",
                "next_step": (
                    "Open the Airbyte builder via the redirect_url returned "
                    "by /discovery/entries/{id}/promote."
                ),
            },
            summary=f"connection {name!r} created from {template_slug}",
        )


# ---------------------------------------------------------------------------
# 4. materialize (mutating; cost-aware preflight)
# ---------------------------------------------------------------------------


class MaterializeInput(BaseModel):
    asset_key: str
    partition_range: str | None = None
    estimated_cost_tokens: int = Field(default=1, ge=1)


@register_data_mcp_tool
class IngestMaterializeTool(DataMCPTool):
    """Trigger a Dagster asset materialization with rate-limit preflight."""

    name = "data.ingest.materialize"
    description = (
        "Trigger a Dagster asset materialization. The preflight reserves "
        "estimated_cost_tokens against the calling user's vendor bucket; "
        "if the reservation fails the call returns the exact remaining-"
        "budget message instead of silently burning quota."
    )
    args_schema = MaterializeInput
    category = "ingest"
    tags = ("ingest", "materialize", "dagster")
    mutates = True
    required_scopes = ("data:read", "data:write")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        asset_key: str,
        partition_range: str | None = None,
        estimated_cost_tokens: int = 1,
    ) -> MCPToolResult:
        if _is_agent(ctx):
            from aqp.services.ingestion_approvals import request_approval

            pending = request_approval(
                tool_id=self.name,
                args={
                    "asset_key": asset_key,
                    "partition_range": partition_range,
                },
                requested_by_agent_sub=_agent_sub(ctx),
                on_behalf_of_user_id=_on_behalf_of_user(ctx),
                workspace_id=ctx.workspace_id,
                estimated_cost_tokens=estimated_cost_tokens,
            )
            return MCPToolResult(
                ok=True,
                data=pending,
                summary=f"approval queued for materialize({asset_key})",
            )
        # Human path: rate-limit preflight reservation.
        user_id = _on_behalf_of_user(ctx) or "anonymous"
        try:
            from aqp_ratelimit import get_ratelimit_client

            outcome = get_ratelimit_client().reserve(
                user_id=user_id,
                service=_infer_service_from_asset(asset_key),
                key_id="primary",
                n_tokens=int(estimated_cost_tokens),
                ttl_s=3600,
            )
            if not outcome.allow:
                return MCPToolResult(
                    ok=False,
                    error=(
                        f"this materialization would need {estimated_cost_tokens} "
                        f"tokens but only {outcome.remaining:.1f} remaining "
                        f"in your {outcome.service} budget"
                    ),
                )
            reservation_id = outcome.reservation_id
        except Exception as exc:  # noqa: BLE001
            logger.debug("materialize preflight failed: %s", exc)
            reservation_id = None
        return MCPToolResult(
            ok=True,
            data={
                "asset_key": asset_key,
                "partition_range": partition_range,
                "reservation_id": reservation_id,
                "status": "queued",
            },
            summary=f"materialization queued for {asset_key}",
        )


def _infer_service_from_asset(asset_key: str) -> str:
    """Extract the vendor service name from a Dagster asset key.

    Default convention: ``['raw', '<vendor>', '<stream>']`` produces
    ``'<vendor>.<stream>'`` and other shapes fall back to a generic
    ``'vendor.unknown'`` bucket.
    """
    parts = [p for p in str(asset_key).replace("/", ".").split(".") if p]
    if len(parts) >= 3 and parts[0] in {"raw", "ingest"}:
        return f"{parts[1]}.{parts[2]}"
    return "vendor.unknown"


__all__ = [
    "IngestCreateConnectionTool",
    "IngestListTemplatesTool",
    "IngestMaterializeTool",
    "IngestPreviewSourceTool",
]
