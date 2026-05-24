"""``strategy.lean_framework`` — LEAN 5-slot (Universe / Alpha / PC / Risk / Execution).

Two modes, picked by params:

1. ``params.lean_source`` — a LEAN QCAlgorithm source string the
   executor translates through
   :func:`aqp.strategies.lean.translator.translate_lean_to_framework`.
   The translated FrameworkAlgorithm skeleton is saved as a
   ``lab_snippets`` row tagged ``language='python'``, and the
   executor returns the snippet id + the rendered source on the
   locator so the user can iterate on it in the snippet editor.
2. ``params.template_resource_id`` — clone an existing
   ``resource_type='strategy_template'`` row through the existing
   ``data.strategies.templates.clone_to_workspace`` MCP tool. The
   cloned :class:`Resource` id is surfaced on the locator.

This executor does NOT instantiate the framework algorithm itself —
running a strategy still goes through :class:`BotRuntime` (rule 14).
Phase 2 is "render + persist"; Phase 4 will optionally pipe the
translated source through a draft GraphSpec that wires it as a
``snippet.python`` upstream of ``strategy.vbt_portfolio``.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.lab.executors._types import NodeContext, NodeResult

logger = logging.getLogger(__name__)


def execute(node: Any, ctx: NodeContext) -> NodeResult:
    params = dict(getattr(node, "params", {}) or {})
    source = params.get("lean_source")
    template_resource_id = params.get("template_resource_id")
    class_name = params.get("class_name")

    if not source and not template_resource_id:
        return NodeResult(
            status="error",
            error=(
                "strategy.lean_framework requires either params.lean_source "
                "(raw QCAlgorithm source) or params.template_resource_id "
                "(an existing resource_type='strategy_template' row)."
            ),
            log_label="strategy.lean_framework:missing_input",
        )

    if source:
        return _translate_inline(node, ctx, source, class_name)

    return _clone_template(node, ctx, str(template_resource_id), params)


def _translate_inline(
    node: Any,
    ctx: NodeContext,
    source: str,
    class_name: Any,
) -> NodeResult:
    try:
        from aqp.strategies.lean.translator import translate_lean_to_framework
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=f"LEAN translator unavailable: {exc}",
            log_label="strategy.lean_framework:no_translator",
        )

    try:
        rendered = translate_lean_to_framework(
            str(source),
            class_name=str(class_name) if class_name else None,
        )
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=f"LEAN translation failed: {exc}",
            log_label="strategy.lean_framework:translate_fail",
        )

    snippet_id: str | None = None
    workspace_id = getattr(ctx.request_context, "workspace_id", None)
    if workspace_id:
        try:
            from aqp.lab.snippets import save_snippet

            snippet_id = save_snippet(
                workspace_id=str(workspace_id),
                name=f"LEAN-translated:{class_name or 'algo'} ({node.id})",
                source=rendered,
                language="python",
                manifest={
                    "source": "lean_translator",
                    "class_name": class_name,
                    "node_id": node.id,
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("save_snippet for LEAN translation failed: %s", exc)
            snippet_id = None

    return NodeResult(
        status="done",
        output_locator={
            "kind": "lean_framework",
            "mode": "translate_inline",
            "snippet_id": snippet_id,
            "rendered_chars": len(rendered),
            "class_name": class_name,
            "node_id": node.id,
        },
        metrics={
            "rendered_chars": int(len(rendered)),
            "snippet_persisted": bool(snippet_id),
        },
        log_label="strategy.lean_framework:translate",
    )


def _clone_template(
    node: Any,
    ctx: NodeContext,
    resource_id: str,
    params: dict[str, Any],
) -> NodeResult:
    """Route through the data.strategies.templates MCP tool (rule 22).

    We instantiate the tool directly here rather than reaching into
    `aqp.persistence.models_resources` so the policy / tenancy
    enforcement the MCP layer applies survives.
    """
    try:
        from aqp.data.mcp.base import MCPToolContext
        from aqp.data.mcp.registry import get_data_mcp_tool
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=f"DataMCP registry import failed: {exc}",
            log_label="strategy.lean_framework:no_mcp",
        )

    try:
        tool = get_data_mcp_tool("data.strategies.templates.clone_to_workspace")
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=(
                "data.strategies.templates.clone_to_workspace MCP tool not "
                f"registered: {exc}"
            ),
            log_label="strategy.lean_framework:no_clone_tool",
        )

    workspace_id = getattr(ctx.request_context, "workspace_id", None)
    project_id = getattr(ctx.request_context, "project_id", None)
    mcp_ctx = MCPToolContext(
        actor="lab_runtime",
        actor_kind="system",
        session_id=ctx.run_id,
        workspace_id=str(workspace_id) if workspace_id else None,
        project_id=str(project_id) if project_id else None,
        granted_scopes=("data:read", "data:write"),
    )
    args = {
        "resource_id": str(resource_id),
        "translate": bool(params.get("translate", True)),
        "target_workspace_id": str(workspace_id) if workspace_id else None,
    }
    if params.get("name"):
        args["name"] = str(params["name"])

    try:
        result = tool.invoke(ctx=mcp_ctx, **args)
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=f"clone_to_workspace failed: {exc}",
            log_label="strategy.lean_framework:clone_fail",
        )
    if not getattr(result, "ok", False):
        return NodeResult(
            status="error",
            error=str(getattr(result, "error", "clone_to_workspace returned ok=false")),
            log_label="strategy.lean_framework:clone_denied",
        )

    data = dict(getattr(result, "data", {}) or {})
    return NodeResult(
        status="done",
        output_locator={
            "kind": "lean_framework",
            "mode": "clone_template",
            "resource_id": data.get("cloned_resource_id") or data.get("resource_id"),
            "template_resource_id": resource_id,
            "translated": bool(params.get("translate", True)),
            "node_id": node.id,
        },
        metrics={
            "translated_chars": int(data.get("translated_chars") or 0),
        },
        log_label=f"strategy.lean_framework:clone:{resource_id}",
    )


__all__ = ["execute"]
