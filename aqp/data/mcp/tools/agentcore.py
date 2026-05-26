"""``data.agentcore.*`` DataMCP tools (Phase E of AWS hybrid rollout).

Read + control-plane surface for Amazon Bedrock AgentCore from agents:

- :class:`ListAgentCoreRuntimesTool`  (``data.agentcore.list_runtimes``)
  — read the registered AgentCore runtimes for the active environment.
- :class:`ListAgentCoreSessionsTool`  (``data.agentcore.list_sessions``)
  — return the most recent ``agent_runs_v2`` rows that were dispatched
  via AgentCore (i.e. ``agentcore_session_id IS NOT NULL``).
- :class:`InvokeAgentCoreTool`        (``data.agentcore.invoke``)
  — mutating; dispatch a one-shot AgentCore invocation by spec name.
  Per AGENTS rule 22 every credential goes through CredentialResolver
  + boto3 chain; the route returns metadata only, never the raw
  AgentCore response payload (the operator inspects the
  ``agent_runs_v2`` row + the AgentCore console for that).

Per AGENTS rule 49 these tools surface through the same
``/.well-known/oauth-protected-resource`` endpoint as every other
data.* tool — the MCP server requires a delegated agent token via
:meth:`AgentRuntime.delegated_token_for_mcp` (rule 54).
"""
from __future__ import annotations

import logging
import os
from typing import Any

from pydantic import BaseModel, Field

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ListRuntimesInput(BaseModel):
    environment: str | None = Field(
        default=None,
        description=(
            "Deployment environment slug. Empty resolves from "
            "``AQP_ENVIRONMENT`` (defaults to 'dev')."
        ),
    )


class ListSessionsInput(BaseModel):
    spec_name: str | None = Field(
        default=None,
        description="Optional spec-name filter.",
    )
    limit: int = Field(default=20, ge=1, le=200)


class InvokeInput(BaseModel):
    spec_name: str = Field(..., description="Registered AgentSpec name.")
    inputs: dict[str, Any] = Field(default_factory=dict)
    runtime_alias: str = Field(
        default="default",
        description=(
            "AgentCore runtime alias. 'default' resolves to "
            "/aqp/${env}/agentcore_runtime_arn; named aliases resolve "
            "to /aqp/${env}/agentcore_runtimes/{alias}/arn."
        ),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_environment(explicit: str | None) -> str:
    if explicit:
        return explicit
    env = os.environ.get("AQP_ENVIRONMENT", "").strip()
    return env or "dev"


def _redact_runtime_arn(arn: str) -> str:
    """Keep the runtime arn family + suffix; mask the account id segment.

    AgentCore runtime ARNs look like
    ``arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/aqp-runtime-dev``
    — the account id is sensitive in audit logs even though the runtime
    name is not.
    """
    parts = arn.split(":")
    if len(parts) >= 6:
        parts[4] = "***ACCOUNT***"
        return ":".join(parts)
    return arn


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@register_data_mcp_tool
class ListAgentCoreRuntimesTool(DataMCPTool):
    """List the registered AgentCore runtimes (via SSM Parameter Store)."""

    name = "data.agentcore.list_runtimes"
    description = (
        "List Bedrock AgentCore runtimes registered for the active "
        "environment. Returns the primary runtime + every named alias. "
        "Account ids in ARNs are redacted."
    )
    args_schema = ListRuntimesInput
    required_scopes = ("data:read",)
    mutates = False

    def run(
        self,
        *,
        ctx: MCPToolContext,
        environment: str | None = None,
    ) -> MCPToolResult:
        env = _resolve_environment(environment)
        try:
            import boto3
        except ImportError:
            return MCPToolResult(
                ok=False,
                error="boto3 not installed; install aqp[bedrock] to use AgentCore MCP",
            )

        ssm = boto3.client("ssm")
        runtimes: list[dict[str, Any]] = []

        try:
            primary = ssm.get_parameter(Name=f"/aqp/{env}/agentcore_runtime_arn")
            arn = str(primary.get("Parameter", {}).get("Value") or "")
            if arn:
                runtimes.append(
                    {
                        "alias": "default",
                        "runtime_arn": _redact_runtime_arn(arn),
                        "environment": env,
                    }
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("primary runtime SSM lookup failed for %s: %s", env, exc)

        try:
            paginator = ssm.get_paginator("get_parameters_by_path")
            for page in paginator.paginate(
                Path=f"/aqp/{env}/agentcore_runtimes/",
                Recursive=True,
            ):
                for param in page.get("Parameters") or []:
                    name = str(param.get("Name") or "")
                    if not name.endswith("/arn"):
                        continue
                    alias = name.split("/")[-2]
                    runtimes.append(
                        {
                            "alias": alias,
                            "runtime_arn": _redact_runtime_arn(
                                str(param.get("Value") or "")
                            ),
                            "environment": env,
                        }
                    )
        except Exception as exc:  # noqa: BLE001
            logger.debug("named-runtime SSM scan failed for %s: %s", env, exc)

        return MCPToolResult(
            ok=True,
            data={"runtimes": runtimes, "environment": env},
            summary=f"{len(runtimes)} runtime(s) registered",
        )


@register_data_mcp_tool
class ListAgentCoreSessionsTool(DataMCPTool):
    """List the most recent agent runs dispatched via AgentCore."""

    name = "data.agentcore.list_sessions"
    description = (
        "List recent agent runs that were dispatched through Bedrock "
        "AgentCore (agentcore_session_id IS NOT NULL). Returns spec "
        "name, status, session id, cost, and duration. Excludes the "
        "raw response payload."
    )
    args_schema = ListSessionsInput
    required_scopes = ("data:read",)
    mutates = False

    def run(
        self,
        *,
        ctx: MCPToolContext,
        spec_name: str | None = None,
        limit: int = 20,
    ) -> MCPToolResult:
        try:
            from aqp.persistence.db import get_session
            from aqp.persistence.models_agents import AgentRunV2
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(
                ok=False,
                error=f"agent_runs_v2 ORM unavailable: {exc}",
            )

        with get_session() as session:
            query = session.query(AgentRunV2)
            if hasattr(AgentRunV2, "agentcore_session_id"):
                query = query.filter(
                    AgentRunV2.agentcore_session_id.isnot(None)
                )
            else:
                return MCPToolResult(
                    ok=True,
                    data={"sessions": []},
                    summary=(
                        "agentcore_session_id column missing — run "
                        "alembic upgrade head to apply migration 0087"
                    ),
                )
            if spec_name:
                query = query.filter(AgentRunV2.spec_name == spec_name)
            rows = (
                query.order_by(AgentRunV2.started_at.desc())
                .limit(int(limit))
                .all()
            )

        sessions: list[dict[str, Any]] = []
        for row in rows:
            sessions.append(
                {
                    "run_id": row.id,
                    "spec_name": row.spec_name,
                    "status": row.status,
                    "session_id": getattr(row, "agentcore_session_id", None),
                    "runtime_arn": _redact_runtime_arn(
                        getattr(row, "agentcore_runtime_arn", "") or ""
                    ),
                    "memory_id": getattr(row, "agentcore_memory_id", None),
                    "cost_usd": float(row.cost_usd or 0.0),
                    "started_at": row.started_at.isoformat() if row.started_at else None,
                    "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                }
            )
        return MCPToolResult(
            ok=True,
            data={"sessions": sessions},
            summary=f"{len(sessions)} AgentCore session(s)",
        )


@register_data_mcp_tool
class InvokeAgentCoreTool(DataMCPTool):
    """One-shot AgentCore Runtime invocation by spec name (mutating)."""

    name = "data.agentcore.invoke"
    description = (
        "Dispatch an AgentSpec via Bedrock AgentCore Runtime. Returns "
        "the run id + status + session id only — the raw response body "
        "is persisted on the agent_runs_v2 row. Mutating: requires "
        "the 'agents:invoke_agentcore' scope."
    )
    args_schema = InvokeInput
    required_scopes = ("agents:invoke_agentcore",)
    mutates = True

    def run(
        self,
        *,
        ctx: MCPToolContext,
        spec_name: str,
        inputs: dict[str, Any] | None = None,
        runtime_alias: str = "default",
    ) -> MCPToolResult:
        try:
            from aqp.agents.registry import get_agent_spec
            from aqp.agents.runtime import AgentRuntime
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(
                ok=False,
                error=f"AgentRuntime unavailable: {exc}",
            )

        try:
            spec = get_agent_spec(spec_name)
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(
                ok=False,
                error=f"unknown AgentSpec {spec_name!r}: {exc}",
            )

        runtime = AgentRuntime(
            spec=spec,
            agentcore_runtime_alias=runtime_alias,
        )
        result = runtime.run(inputs or {})
        return MCPToolResult(
            ok=result.status == "completed",
            data={
                "run_id": result.run_id,
                "spec_name": result.spec_name,
                "status": result.status,
                "session_id": runtime._agentcore_session_id,  # noqa: SLF001 — owned by us
                "runtime_arn": _redact_runtime_arn(
                    runtime._agentcore_runtime_arn or ""  # noqa: SLF001
                ),
                "cost_usd": float(result.cost_usd or 0.0),
                "error": result.error,
            },
            summary=f"AgentCore invocation: {result.status}",
        )


__all__ = [
    "InvokeAgentCoreTool",
    "ListAgentCoreRuntimesTool",
    "ListAgentCoreSessionsTool",
]
