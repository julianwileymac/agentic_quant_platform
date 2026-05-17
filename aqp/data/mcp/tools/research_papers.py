"""DataMCP tools for the math-aware research-paper corpus.

Exposes ``data.research_papers.browse`` / ``.search`` / ``.synthesize``
so spec-driven agents can ground their reasoning in the indexed
papers without bypassing the :class:`DataMCPTool` boundary
(AGENTS.md rule 22).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool


class BrowsePapersInput(BaseModel):
    strategy_family: str | None = Field(default=None)
    author_institution: str | None = Field(default=None)
    contains_mathematics: bool | None = Field(default=None)
    limit: int = Field(default=20, ge=1, le=500)


@register_data_mcp_tool
class BrowseResearchPapersTool(DataMCPTool):
    name = "data.research_papers.browse"
    description = (
        "Browse the research-paper corpus. Returns a paginated list of papers with "
        "their title / authors / institution / strategy family / equation count."
    )
    args_schema = BrowsePapersInput
    category = "research_papers"
    tags = ("rag", "papers", "browse")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        strategy_family: str | None = None,
        author_institution: str | None = None,
        contains_mathematics: bool | None = None,
        limit: int = 20,
    ) -> MCPToolResult:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_research_papers import ResearchPaperRow

        rows: list[dict[str, Any]] = []
        with SessionLocal() as session:
            q = session.query(ResearchPaperRow).order_by(
                ResearchPaperRow.created_at.desc()
            )
            if strategy_family:
                q = q.filter(ResearchPaperRow.strategy_family == strategy_family)
            if author_institution:
                q = q.filter(
                    ResearchPaperRow.author_institution == author_institution
                )
            if contains_mathematics is not None:
                q = q.filter(
                    ResearchPaperRow.contains_mathematics == contains_mathematics
                )
            for row in q.limit(limit).all():
                rows.append(
                    {
                        "id": str(row.id),
                        "title": row.title,
                        "authors": list(row.authors or []),
                        "author_institution": row.author_institution,
                        "publication_year": row.publication_year,
                        "strategy_family": row.strategy_family,
                        "contains_mathematics": row.contains_mathematics,
                        "equation_count": row.equation_count,
                    }
                )
        return MCPToolResult(
            ok=True,
            data=rows,
            rows_returned=len(rows),
            summary=f"{len(rows)} research papers",
        )


class SearchPapersInput(BaseModel):
    query: str = Field(..., description="Hybrid search query (dense + sparse).")
    k: int = Field(default=10, ge=1, le=50)
    dense_weight: float = Field(default=1.0, ge=0.0, le=10.0)
    sparse_weight: float = Field(default=1.0, ge=0.0, le=10.0)


@register_data_mcp_tool
class SearchResearchPapersTool(DataMCPTool):
    name = "data.research_papers.search"
    description = (
        "Hybrid dense + sparse search over the research-paper corpus. Useful when "
        "exact-token matches (author names, theorem numbers, variable symbols) need "
        "to be retrieved alongside semantic similarity."
    )
    args_schema = SearchPapersInput
    category = "research_papers"
    tags = ("rag", "papers", "search", "hybrid")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        query: str,
        k: int = 10,
        dense_weight: float = 1.0,
        sparse_weight: float = 1.0,
    ) -> MCPToolResult:
        from aqp.rag import get_default_rag

        hits = get_default_rag().query_hybrid(
            query=query,
            corpus="research_papers",
            level="l2",
            k=k,
            dense_weight=dense_weight,
            sparse_weight=sparse_weight,
        )
        out = [
            {
                "doc_id": h.doc_id,
                "text": h.text,
                "score": float(h.score),
                "meta": h.meta or {},
            }
            for h in hits
        ]
        return MCPToolResult(
            ok=True,
            data=out,
            rows_returned=len(out),
            summary=f"hybrid search returned {len(out)} hits",
        )


class SynthesizePapersInput(BaseModel):
    paper_id: str = Field(..., description="Research paper id to synthesise from.")


@register_data_mcp_tool
class SynthesizeResearchPaperTool(DataMCPTool):
    name = "data.research_papers.synthesize"
    description = (
        "Ask the platform LLM to draft an AQP strategy YAML grounded in the chunks "
        "indexed for the given research paper. Routes through router_complete + "
        "HierarchicalRAG so the response is grounded and audited."
    )
    args_schema = SynthesizePapersInput
    category = "research_papers"
    tags = ("rag", "papers", "synthesize")
    required_scopes = ("data:read",)
    mutates = False

    def run(
        self,
        *,
        ctx: MCPToolContext,
        paper_id: str,
    ) -> MCPToolResult:
        from aqp.tasks.research_paper_tasks import synthesize_strategy_impl

        result = synthesize_strategy_impl(paper_id=paper_id)
        return MCPToolResult(
            ok=True,
            data=result,
            summary=f"synthesised strategy for paper {paper_id}",
        )


__all__ = [
    "BrowseResearchPapersTool",
    "SearchResearchPapersTool",
    "SynthesizeResearchPaperTool",
]
