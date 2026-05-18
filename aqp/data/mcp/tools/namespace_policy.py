"""Iceberg namespace policy DataMCP tools."""
from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from aqp.data.catalog.namespace_policy import EffectivePolicy, resolve_policy
from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.policy import enforce_read_only_for_session
from aqp.data.mcp.registry import register_data_mcp_tool
from aqp.metadata import write_aspect
from aqp.metadata.openmetadata import IcebergNamespacePolicy
from aqp.persistence.db import get_session

logger = logging.getLogger(__name__)


def _extract_validation_fields(exc: ValidationError) -> list[str]:
    """Flatten Pydantic ``loc`` tuples to dotted field paths."""
    fields: list[str] = []
    for error in exc.errors():
        location = error.get("loc", ())
        if not location:
            continue
        dotted = ".".join(str(part) for part in location if part != "__root__")
        if dotted and dotted not in fields:
            fields.append(dotted)
    return fields


def _policy_to_dict(policy: EffectivePolicy, *, scope_urn: str | None) -> dict[str, object]:
    """Serialize :class:`EffectivePolicy` for MCP responses."""
    return {
        "scope_urn": scope_urn,
        "bronze_prefix": policy.bronze_prefix,
        "silver_prefix": policy.silver_prefix,
        "gold_prefix": policy.gold_prefix,
        "forbidden_prefixes": sorted(policy.forbidden_prefixes),
        "allowed_extra_prefixes": sorted(policy.allowed_extra_prefixes),
        "source": policy.source,
    }


def _default_scope_urn(ctx: MCPToolContext) -> str | None:
    workspace_id = str(ctx.workspace_id or "").strip()
    if workspace_id:
        return f"urn:aqp:workspace:prod:{workspace_id}"
    return None


class GetNamespacePolicyArgs(BaseModel):
    """Arguments for ``iceberg.namespace_policy.get``."""

    model_config = ConfigDict(extra="forbid")

    scope_urn: str | None = Field(
        default=None,
        description=(
            "Optional scope URN (workspace/project/lab/org). "
            "Defaults to the active workspace when omitted."
        ),
    )


@register_data_mcp_tool
class GetNamespacePolicyTool(DataMCPTool):
    """Return effective namespace policy for one scope."""

    name = "iceberg.namespace_policy.get"
    description = (
        "Return the effective Iceberg namespace policy for a scope URN. "
        "Defaults to the active workspace if scope_urn is omitted."
    )
    args_schema = GetNamespacePolicyArgs
    category = "iceberg"
    tags = ("iceberg", "policy", "read")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        scope_urn: str | None = None,
    ) -> MCPToolResult:
        effective_scope = scope_urn or _default_scope_urn(ctx)
        policy = resolve_policy(scope_urn=effective_scope, context=ctx)
        return MCPToolResult(
            ok=True,
            data=_policy_to_dict(policy, scope_urn=effective_scope),
            summary=(
                "resolved default namespace policy"
                if policy.source == "default"
                else "resolved namespace policy from aspect"
            ),
        )


class SetNamespacePolicyArgs(BaseModel):
    """Arguments for ``iceberg.namespace_policy.set``."""

    model_config = ConfigDict(extra="forbid")

    scope_urn: str = Field(
        ...,
        description=(
            "AQP URN of the entity this policy applies to "
            "(workspace / project / lab / org)."
        ),
    )
    bronze_prefix: str = Field(default="aqp_bronze_")
    silver_prefix: str = Field(default="aqp_silver_")
    gold_prefix: str = Field(default="aqp_gold_")
    allowed_extra_prefixes: list[str] = Field(default_factory=list)
    forbidden_prefixes: list[str] = Field(default_factory=list)


@register_data_mcp_tool
class SetNamespacePolicyTool(DataMCPTool):
    """Write an ``icebergNamespacePolicy`` aspect for a scope."""

    name = "iceberg.namespace_policy.set"
    description = (
        "Write an icebergNamespacePolicy aspect for a scope URN. "
        "Requires data:write."
    )
    args_schema = SetNamespacePolicyArgs
    category = "iceberg"
    tags = ("iceberg", "policy", "mutating")
    required_scopes = ("data:read", "data:write")
    mutates = True

    def policy_check(self, ctx: MCPToolContext) -> None:
        super().policy_check(ctx)
        enforce_read_only_for_session(ctx, mutates=True)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        scope_urn: str,
        bronze_prefix: str = "aqp_bronze_",
        silver_prefix: str = "aqp_silver_",
        gold_prefix: str = "aqp_gold_",
        allowed_extra_prefixes: list[str] | None = None,
        forbidden_prefixes: list[str] | None = None,
    ) -> MCPToolResult:
        _ = ctx
        try:
            policy = IcebergNamespacePolicy(
                scope_urn=scope_urn,
                bronze_prefix=bronze_prefix,
                silver_prefix=silver_prefix,
                gold_prefix=gold_prefix,
                allowed_extra_prefixes=list(allowed_extra_prefixes or []),
                forbidden_prefixes=list(forbidden_prefixes or []),
            )
        except ValidationError as exc:
            fields = _extract_validation_fields(exc)
            return MCPToolResult(
                ok=False,
                error="MetadataValidationError",
                metadata={
                    "fields": fields,
                    "guidance": "one or more namespace policy fields are invalid",
                    "details": exc.errors(),
                },
            )

        with get_session() as session:
            aspect = write_aspect(
                session,
                policy.scope_urn,
                IcebergNamespacePolicy.aspect_name,
                policy,
            )
            session.commit()
        resolved = resolve_policy(scope_urn=policy.scope_urn)
        return MCPToolResult(
            ok=True,
            data={
                "aspect_id": str(aspect.id),
                "version": int(aspect.version),
                **_policy_to_dict(resolved, scope_urn=policy.scope_urn),
            },
            summary=f"wrote namespace policy for {policy.scope_urn}",
        )


__all__ = ["GetNamespacePolicyTool", "SetNamespacePolicyTool"]
