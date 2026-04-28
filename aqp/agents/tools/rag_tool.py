"""CrewAI tools that expose the hierarchical RAG to agents."""
from __future__ import annotations

from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class RagQueryInput(BaseModel):
    query: str = Field(..., description="Natural-language question or topic.")
    level: str = Field(default="l3", description="One of l0|l1|l2|l3.")
    corpus: str | None = Field(default=None)
    order: str | None = Field(default=None, description="first|second|third")
    vt_symbol: str | None = Field(default=None)
    k: int = Field(default=8, ge=1, le=50)


class RagQueryTool(BaseTool):
    name: str = "rag_query"
    description: str = (
        "Query the hierarchical RAG. Use level=l3 for specific document chunks, "
        "level=l1/l2 for category-level summaries, level=l0 for past decisions."
    )
    args_schema: type[BaseModel] = RagQueryInput

    def _run(  # type: ignore[override]
        self,
        query: str,
        level: str = "l3",
        corpus: str | None = None,
        order: str | None = None,
        vt_symbol: str | None = None,
        k: int = 8,
    ) -> str:
        try:
            from aqp.rag import get_default_rag

            hits = get_default_rag().query(
                query,
                level=level,
                corpus=corpus,
                order=order,
                vt_symbol=vt_symbol,
                k=k,
            )
        except Exception as exc:  # noqa: BLE001
            return f"ERROR: rag_query failed: {exc}"
        if not hits:
            return "No RAG hits."
        return "\n".join(
            f"{i}. [{h.corpus}/{h.level}] (score={h.score:.3f}) {h.text[:400]}"
            for i, h in enumerate(hits, 1)
        )


class HierarchyBrowseInput(BaseModel):
    query: str = Field(..., description="Topic to navigate")
    levels: list[str] = Field(default_factory=lambda: ["l0", "l1", "l2", "l3"])
    orders: list[str] = Field(default_factory=lambda: ["first", "second", "third"])
    final_k: int = Field(default=8, ge=1, le=20)


class HierarchyBrowseTool(BaseTool):
    name: str = "hierarchy_browse"
    description: str = (
        "Top-down navigation through the four-level RAG hierarchy "
        "(Alpha-GPT autonomous-mode walk)."
    )
    args_schema: type[BaseModel] = HierarchyBrowseInput

    def _run(  # type: ignore[override]
        self,
        query: str,
        levels: list[str] | None = None,
        orders: list[str] | None = None,
        final_k: int = 8,
    ) -> str:
        try:
            from aqp.rag import RAGPlan, get_default_rag

            plan = RAGPlan(
                query=query,
                levels=tuple(levels or ["l0", "l1", "l2", "l3"]),
                orders=tuple(orders or ["first", "second", "third"]),
                final_k=final_k,
            )
            hits = get_default_rag().walk(plan)
        except Exception as exc:  # noqa: BLE001
            return f"ERROR: hierarchy_browse failed: {exc}"
        if not hits:
            return "No hits."
        return "\n".join(
            f"{i}. L={h.level} order={h.order} corpus={h.corpus} score={h.score:.3f}\n   {h.text[:300]}"
            for i, h in enumerate(hits, 1)
        )


__all__ = ["HierarchyBrowseTool", "RagQueryTool"]
