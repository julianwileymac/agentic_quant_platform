"""Arize Phoenix DataMCP tools.

Phase 2d of the AQP infra-expansion plan exposes the Phoenix LLM /
agent / RAG observability layer to agents. Three tools:

- ``data.observability.phoenix.list_projects`` — discovery.
- ``data.observability.phoenix.get_trace`` — single trace by ID.
- ``data.observability.phoenix.annotate_span`` — attach an evaluator
  / human verdict to a span (write).

All tools resolve the Phoenix UI URL from
``settings.phoenix_ui_url`` (topology fallback in Phase 0). Reads
walk the Phoenix REST API (``/v1/projects``, ``/v1/traces/<id>``);
writes use ``/v1/spans/<id>/annotations`` per the Phoenix release
notes.

The annotate tool is the only mutator here; access is controlled by
the agent runtime's tool-policy system (rule 22) so only spec-driven
agents with the right tool list can call it.
"""
from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, Field

from aqp.config import settings
from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool


def _phoenix_root() -> str:
    """Return the Phoenix UI URL stripped of trailing slash, or empty."""
    url = settings.phoenix_ui_url or settings.phoenix_endpoint or ""
    return url.rstrip("/") if url else ""


class ListProjectsInput(BaseModel):
    pass


@register_data_mcp_tool
class PhoenixListProjectsTool(DataMCPTool):
    name = "data.observability.phoenix.list_projects"
    description = "List Arize Phoenix projects (one per AQP service)."
    args_schema = ListProjectsInput
    category = "observability"
    tags = ("phoenix", "ai", "observability")

    def run(self, *, ctx: MCPToolContext) -> MCPToolResult:
        root = _phoenix_root()
        if not root:
            return MCPToolResult(ok=False, error="phoenix_ui_url unset")
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(f"{root}/v1/projects")
                resp.raise_for_status()
                payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=f"phoenix list_projects: {exc}")
        projects = payload.get("data", payload) if isinstance(payload, dict) else payload
        return MCPToolResult(
            ok=True,
            data=projects,
            rows_returned=len(projects) if isinstance(projects, list) else 0,
            summary=(
                f"phoenix projects: {len(projects)}"
                if isinstance(projects, list)
                else "phoenix projects"
            ),
        )


class GetTraceInput(BaseModel):
    trace_id: str = Field(..., description="OTel trace ID (hex).")
    project: str | None = Field(default=None, description="Phoenix project name.")


@register_data_mcp_tool
class PhoenixGetTraceTool(DataMCPTool):
    name = "data.observability.phoenix.get_trace"
    description = (
        "Fetch a single LLM / agent trace by trace_id from Phoenix. Returns "
        "the full span tree with OpenInference attributes (llm.model_name, "
        "tool_calls, etc.)."
    )
    args_schema = GetTraceInput
    category = "observability"
    tags = ("phoenix", "ai", "tracing")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        trace_id: str,
        project: str | None = None,
    ) -> MCPToolResult:
        root = _phoenix_root()
        if not root:
            return MCPToolResult(ok=False, error="phoenix_ui_url unset")
        params: dict[str, Any] = {}
        if project:
            params["project_name"] = project
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(
                    f"{root}/v1/traces/{trace_id}",
                    params=params,
                )
                resp.raise_for_status()
                payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=f"phoenix get_trace: {exc}")
        return MCPToolResult(
            ok=True,
            data=payload,
            summary=f"phoenix trace_id={trace_id} fetched",
        )


class AnnotateSpanInput(BaseModel):
    span_id: str = Field(..., description="OTel span ID (hex).")
    annotation_type: str = Field(
        ...,
        description="Annotation kind (e.g., 'human_verdict', 'eval_score').",
    )
    label: str | None = Field(default=None)
    score: float | None = Field(default=None)
    explanation: str | None = Field(default=None)


@register_data_mcp_tool
class PhoenixAnnotateSpanTool(DataMCPTool):
    name = "data.observability.phoenix.annotate_span"
    description = (
        "Attach an evaluator / human verdict annotation to a Phoenix span. "
        "Used by the analysis-AGENTS evaluation flow to write back evaluator "
        "outcomes (faithfulness, correctness, tool-selection scores)."
    )
    args_schema = AnnotateSpanInput
    category = "observability"
    tags = ("phoenix", "ai", "evals")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        span_id: str,
        annotation_type: str,
        label: str | None = None,
        score: float | None = None,
        explanation: str | None = None,
    ) -> MCPToolResult:
        root = _phoenix_root()
        if not root:
            return MCPToolResult(ok=False, error="phoenix_ui_url unset")
        body: dict[str, Any] = {
            "annotation_type": annotation_type,
        }
        if label is not None:
            body["label"] = label
        if score is not None:
            body["score"] = float(score)
        if explanation is not None:
            body["explanation"] = explanation
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(
                    f"{root}/v1/spans/{span_id}/annotations",
                    json=body,
                )
                resp.raise_for_status()
                payload = resp.json() if resp.text else {"ok": True}
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=f"phoenix annotate_span: {exc}")
        return MCPToolResult(
            ok=True,
            data=payload,
            summary=f"phoenix span={span_id} annotated ({annotation_type})",
        )


__all__ = [
    "PhoenixAnnotateSpanTool",
    "PhoenixGetTraceTool",
    "PhoenixListProjectsTool",
]
