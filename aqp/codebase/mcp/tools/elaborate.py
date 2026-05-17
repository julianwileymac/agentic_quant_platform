"""``codebase.elaborate_finding`` — short LLM summary of a code region.

This is the ONE tool in the codebase MCP that calls an LLM. Per
AGENTS rule 2 it routes through :func:`router_complete`; per rule 26
any external endpoint resolves credentials through
:class:`aqp.credentials.CredentialResolver` (handled inside the
router).
"""
from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel, Field

from aqp.codebase.mcp.base import CodebaseMCPTool, MCPToolContext, MCPToolResult
from aqp.codebase.mcp.policy import (
    enforce_no_secret_globs,
    enforce_path_inside_workspace,
)
from aqp.codebase.mcp.registry import register_codebase_mcp_tool

logger = logging.getLogger(__name__)


class ElaborateInput(BaseModel):
    file: str = Field(..., description="Workspace path of the file to elaborate on.")
    start_line: int = Field(..., ge=1)
    end_line: int = Field(..., ge=1)
    question: str | None = Field(
        default=None,
        description="Optional follow-up question to anchor the elaboration.",
    )
    model_alias: str | None = Field(
        default=None,
        description="Optional model alias override (e.g. 'sera' once SERA-32B is wired).",
    )
    max_tokens: int = Field(default=200, ge=32, le=1024)


def _read_region(file_path: Path, start_line: int, end_line: int) -> str:
    text = file_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    lo = max(0, int(start_line) - 1)
    hi = min(len(lines), int(end_line))
    return "\n".join(lines[lo:hi])


@register_codebase_mcp_tool
class ElaborateFindingTool(CodebaseMCPTool):
    name = "codebase.elaborate_finding"
    description = (
        "Summarise a region of code in ≤200 tokens via router_complete "
        "(quick tier by default). The tool reads the lines, builds a tight "
        "prompt, and returns the model's natural-language explanation. Use "
        "this after codebase.search to interpret a hit without pulling the "
        "entire file into the agent context."
    )
    args_schema = ElaborateInput
    category = "explain"
    tags = ("codebase", "explain", "router_complete")
    required_scopes = ("code:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        file: str,
        start_line: int,
        end_line: int,
        question: str | None = None,
        model_alias: str | None = None,
        max_tokens: int = 200,
    ) -> MCPToolResult:
        file_path = enforce_path_inside_workspace(ctx, file)
        enforce_no_secret_globs(ctx, file_path)
        if not file_path.is_file():
            return MCPToolResult(
                ok=False, error=f"file {file!r} not found", summary="missing file"
            )
        region = _read_region(file_path, start_line, end_line)
        if not region.strip():
            return MCPToolResult(
                ok=False, error="region is empty", summary="empty region"
            )

        prompt = (
            "You are a senior engineer reviewing a slice of the AQP "
            "(agentic quant platform) codebase. Summarise the snippet "
            "in at most 5 short sentences. Note any side effects, "
            "external calls, and AGENTS hard-rule relevance. If the "
            "user asked a question, answer it explicitly.\n\n"
            f"File: {file_path}\n"
            f"Lines: {start_line}-{end_line}\n\n"
            "```\n" + region + "\n```\n\n"
            + (f"Question: {question}\n" if question else "")
        )

        try:
            from aqp.llm.providers.router import router_complete
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(
                ok=False,
                error=f"router_complete unavailable: {exc}",
                summary="LLM router unavailable",
            )

        try:
            response = router_complete(
                messages=[
                    {"role": "system", "content": "You explain code accurately and tersely."},
                    {"role": "user", "content": prompt},
                ],
                tier="quick",
                max_tokens=int(max_tokens),
                model_alias=model_alias,
            )
        except TypeError:
            # Older router_complete signatures don't accept model_alias.
            try:
                response = router_complete(  # type: ignore[call-arg]
                    messages=[
                        {"role": "system", "content": "You explain code accurately and tersely."},
                        {"role": "user", "content": prompt},
                    ],
                    tier="quick",
                    max_tokens=int(max_tokens),
                )
            except Exception as exc:  # noqa: BLE001
                return MCPToolResult(
                    ok=False, error=f"router_complete failed: {exc}", summary="LLM call failed"
                )
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(
                ok=False, error=f"router_complete failed: {exc}", summary="LLM call failed"
            )

        # ``router_complete`` returns a string or a dict-like message
        # depending on the installed router version; be defensive.
        if isinstance(response, dict):
            text = (
                response.get("content")
                or response.get("text")
                or response.get("message", {}).get("content", "")
            )
        else:
            text = str(response)
        return MCPToolResult(
            ok=True,
            data={
                "file": str(file_path),
                "start_line": start_line,
                "end_line": end_line,
                "elaboration": text,
                "model_alias": model_alias or "quick",
            },
            summary="elaborated finding",
        )


__all__: list[str] = []
