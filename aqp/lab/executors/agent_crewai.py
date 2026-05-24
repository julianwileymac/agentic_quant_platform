"""``agent.crewai`` — dispatch a CrewAI / LangGraph agent via AgentRuntime.

AGENTS rule 12 — every spec-driven agent run goes through
:class:`aqp.agents.runtime.AgentRuntime`. This executor:

1. Resolves the ``AgentSpec`` referenced by ``params.agent_spec``.
2. Constructs the agent prompt from upstream artifacts (tearsheet,
   RAG hits, run metrics) — never reads ORM directly (rule 22).
3. Calls ``AgentRuntime.run(...)``; persists the agent's output as
   a ``lab_notes`` row attached to the active graph + run.

The prebuilt graph the plan calls out (tearsheet + 2 RAG hits → 1-page
analysis) wires this executor as its terminal node; all data flows
through DataMCP tools or the upstream node locators — no direct
Postgres / Iceberg reads from agent code.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.lab.executors._types import NodeContext, NodeResult

logger = logging.getLogger(__name__)


def _build_context_prompt(ctx: NodeContext) -> str:
    """Render upstream locators into a prompt fragment.

    Agents must not read ORM rows directly (AGENTS rule 22); the
    upstream locators already carry the artifact URIs + summary
    metrics the agent needs, so we serialise those into a string.
    """
    parts: list[str] = []
    for port_name, locator in (ctx.upstream or {}).items():
        if not isinstance(locator, dict):
            continue
        kind = locator.get("kind") or "unknown"
        parts.append(f"- input '{port_name}' ({kind}): {locator}")
    if not parts:
        return "(no upstream artifacts attached)"
    return "Upstream artifacts:\n" + "\n".join(parts)


def _fetch_paper_context(lab_id: str | None, query: str, k: int) -> str:
    """Optionally enrich the agent's prompt with RAG hits.

    Reads through the canonical ``data.research_papers.search`` MCP
    tool (rule 22) so the agent sees the same chunks the operator
    would see in the PaperRagDrawer. Best-effort: returns an empty
    string when the tool is missing.
    """
    if not lab_id or not query:
        return ""
    try:
        from aqp.data.mcp.base import MCPToolContext
        from aqp.data.mcp.registry import get_data_mcp_tool

        tool = get_data_mcp_tool("data.research_papers.search")
    except Exception:  # noqa: BLE001
        return ""
    try:
        mcp_ctx = MCPToolContext(
            actor="lab_runtime",
            actor_kind="system",
            granted_scopes=("data:read",),
        )
        result = tool.invoke(ctx=mcp_ctx, query=query, k=int(k))
    except Exception:  # noqa: BLE001
        return ""
    data = getattr(result, "data", None)
    if not isinstance(data, dict):
        return ""
    hits = data.get("hits") or data.get("items") or []
    if not isinstance(hits, list) or not hits:
        return ""
    rendered = ["Paper RAG hits:"]
    for hit in hits[: max(1, int(k))]:
        title = hit.get("paper_title") or hit.get("title") or "?"
        chunk_id = hit.get("chunk_id") or hit.get("id") or "?"
        text = str(hit.get("text") or "")[:600]
        rendered.append(f"- {{title: {title!r}, chunk_id: {chunk_id!r}}}: {text}")
    return "\n".join(rendered)


def execute(node, ctx: NodeContext) -> NodeResult:
    params = dict(getattr(node, "params", {}) or {})
    agent_spec_name = str(params.get("agent_spec") or "").strip()
    prompt_prefix = str(params.get("prompt") or "").strip()
    persist_as_note = bool(params.get("persist_as_note", True))
    note_target_kind = str(params.get("note_target_kind") or "run")
    note_target_id = str(params.get("note_target_id") or ctx.run_id)
    # Phase 5 extensions — agent.crewai can pull richer context.
    tools_override = params.get("tools")
    paper_query = str(params.get("paper_query") or prompt_prefix or "").strip()
    paper_k = int(params.get("paper_k") or 0)

    if not agent_spec_name:
        return NodeResult(
            status="error",
            error="agent.crewai requires 'agent_spec' (a registered AgentSpec name)",
        )

    try:
        from aqp.agents.registry import get_agent_spec
        from aqp.agents.runtime import AgentRuntime
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=f"AgentRuntime unavailable: {exc}",
        )

    try:
        agent_spec = get_agent_spec(agent_spec_name)
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=f"AgentSpec {agent_spec_name!r} not found: {exc}",
        )

    upstream_text = _build_context_prompt(ctx)
    rag_text = (
        _fetch_paper_context(
            getattr(ctx.request_context, "lab_id", None), paper_query, paper_k
        )
        if paper_k > 0
        else ""
    )
    composed_prompt_parts: list[str] = []
    if prompt_prefix:
        composed_prompt_parts.append(prompt_prefix)
    composed_prompt_parts.append(upstream_text)
    if rag_text:
        composed_prompt_parts.append(rag_text)
    composed_prompt_parts.append(
        "Write a one-page analysis. Cite any RAG hits you reference by "
        "{paper_title, chunk_id}."
    )
    composed_prompt = "\n\n".join(composed_prompt_parts)

    # When tools_override is provided, build a per-run spec that
    # narrows the tool list to the requested allowlist. We model_copy
    # via model_dump + model_validate to keep the immutability rule
    # (rule 13) intact — the original spec stays unchanged.
    runtime_spec = agent_spec
    if isinstance(tools_override, list) and tools_override:
        try:
            spec_dict = agent_spec.model_dump(mode="json")
            spec_dict["tools"] = [str(t) for t in tools_override]
            from aqp.agents.spec import AgentSpec  # noqa: PLC0415

            runtime_spec = AgentSpec.model_validate(spec_dict)
        except Exception:  # noqa: BLE001
            pass

    runtime = AgentRuntime(
        spec=runtime_spec,
        run_id=ctx.run_id,
        task_id=ctx.task_id,
        context=ctx.request_context,
    )
    try:
        result = runtime.run(inputs={"prompt": composed_prompt})
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=f"AgentRuntime.run crashed: {exc}",
        )

    output = getattr(result, "output", {}) or {}
    text = ""
    if isinstance(output, dict):
        for key in ("text", "content", "message", "answer", "summary"):
            val = output.get(key)
            if isinstance(val, str) and val.strip():
                text = val
                break

    note_id: str | None = None
    if persist_as_note and text:
        try:
            from datetime import datetime
            from uuid import uuid4

            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_lab import LabNote

            with SessionLocal() as session:
                note = LabNote(
                    id=str(uuid4()),
                    lab_id=getattr(ctx.request_context, "lab_id", None) or "",
                    target_kind=note_target_kind,
                    target_id=note_target_id,
                    body_md=text,
                    citations=[],
                    created_at=datetime.utcnow(),
                )
                session.add(note)
                session.commit()
                note_id = note.id
        except Exception:  # noqa: BLE001
            logger.debug("agent.crewai could not persist note", exc_info=True)

    return NodeResult(
        status=getattr(result, "status", "done"),
        output_locator={
            "kind": "agent_output",
            "agent_spec": agent_spec_name,
            "text": text,
            "note_id": note_id,
            "n_calls": getattr(result, "n_calls", 0),
            "cost_usd": getattr(result, "cost_usd", 0.0),
            "node_id": node.id,
        },
        metrics={
            "n_calls": int(getattr(result, "n_calls", 0) or 0),
            "cost_usd": float(getattr(result, "cost_usd", 0.0) or 0.0),
            "n_tool_calls": int(getattr(result, "n_tool_calls", 0) or 0),
            "n_rag_hits": int(getattr(result, "n_rag_hits", 0) or 0),
        },
        log_label=f"agent_crewai:{agent_spec_name}",
    )
