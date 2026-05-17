"""Source registry / setup-wizard DataMCP tools."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from aqp.data.fetchers.factory import get_default_factory
from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.policy import enforce_read_only_for_session
from aqp.data.mcp.registry import register_data_mcp_tool


class ListSourcesInput(BaseModel):
    domain: str | None = None
    requires_auth: bool | None = None
    limit: int = Field(default=50, ge=1, le=500)


@register_data_mcp_tool
class ListSourcesTool(DataMCPTool):
    name = "data.sources.list"
    description = (
        "List registered data extractors / source nodes via the "
        "DataExtractorFactory."
    )
    args_schema = ListSourcesInput
    category = "sources"
    tags = ("sources", "list")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        domain: str | None = None,
        requires_auth: bool | None = None,
        limit: int = 50,
    ) -> MCPToolResult:
        factory = get_default_factory()
        rows = factory.list_extractors()
        if domain:
            rows = [row for row in rows if domain in row.domains]
        if requires_auth is not None:
            rows = [row for row in rows if row.requires_auth == bool(requires_auth)]
        rows = rows[:limit]
        data = [row.to_json() for row in rows]
        return MCPToolResult(
            ok=True,
            data=data,
            rows_returned=len(data),
            summary=f"listed {len(data)} sources",
        )


class GetSetupWizardInput(BaseModel):
    name: str = Field(..., description="Wizard alias eg. 'alpha_vantage'.")


@register_data_mcp_tool
class GetSetupWizardTool(DataMCPTool):
    name = "data.sources.get_wizard"
    description = (
        "Return the setup-wizard descriptor for a source. Read-only; "
        "actually running the wizard requires data:write."
    )
    args_schema = GetSetupWizardInput
    category = "sources"
    tags = ("sources", "wizards")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        name: str,
    ) -> MCPToolResult:
        try:
            from aqp.data.sources.setup_wizards import get_wizard
        except ImportError:
            return MCPToolResult(
                ok=False, error="setup_wizards module unavailable"
            )
        wizard = get_wizard(name)
        if wizard is None:
            return MCPToolResult(ok=False, error=f"unknown wizard {name!r}")
        if hasattr(wizard, "to_dict"):
            data: Any = wizard.to_dict()
        elif hasattr(wizard, "model_dump"):
            data = wizard.model_dump()
        else:
            data = {"name": getattr(wizard, "name", name)}
        return MCPToolResult(ok=True, data=data, summary=f"wizard {name}")


class RunSetupWizardInput(BaseModel):
    name: str = Field(...)
    step_id: str = Field(...)
    inputs: dict[str, Any] = Field(default_factory=dict)


@register_data_mcp_tool
class RunSetupWizardTool(DataMCPTool):
    name = "data.sources.run_wizard"
    description = "Run one step of a setup wizard. Requires data:write scope."
    args_schema = RunSetupWizardInput
    category = "sources"
    tags = ("sources", "wizards", "mutating")
    mutates = True
    required_scopes = ("data:read", "data:write")

    def policy_check(self, ctx: MCPToolContext) -> None:  # noqa: D401
        super().policy_check(ctx)
        enforce_read_only_for_session(ctx, mutates=True)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        name: str,
        step_id: str,
        inputs: dict[str, Any] | None = None,
    ) -> MCPToolResult:
        try:
            from aqp.data.sources.setup_wizards import get_wizard
        except ImportError:
            return MCPToolResult(
                ok=False, error="setup_wizards module unavailable"
            )
        wizard = get_wizard(name)
        if wizard is None:
            return MCPToolResult(ok=False, error=f"unknown wizard {name!r}")
        run_step = getattr(wizard, "run_step", None)
        if not callable(run_step):
            return MCPToolResult(
                ok=False,
                error=f"wizard {name!r} does not expose a run_step method",
            )
        try:
            outcome = run_step(step_id, dict(inputs or {}))
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=f"wizard step failed: {exc}")
        if hasattr(outcome, "to_dict"):
            data: Any = outcome.to_dict()
        elif hasattr(outcome, "model_dump"):
            data = outcome.model_dump()
        elif isinstance(outcome, dict):
            data = outcome
        else:
            data = {"result": str(outcome)}
        return MCPToolResult(
            ok=True,
            data=data,
            summary=f"ran wizard {name} step {step_id}",
        )


__all__ = ["GetSetupWizardTool", "ListSourcesTool", "RunSetupWizardTool"]
