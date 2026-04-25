"""ChromaDB search tools — semantic discovery over local datasets & memory."""
from __future__ import annotations

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from aqp.data.chroma_store import ChromaStore


class ChromaSearchInput(BaseModel):
    query: str = Field(..., description="Natural-language description of the dataset you need.")
    k: int = Field(default=5, description="Number of results to return.")


class ChromaSearchTool(BaseTool):
    name: str = "chroma_search"
    description: str = (
        "Semantic search over indexed local datasets. Returns a ranked list of Parquet files "
        "with their schema and date range."
    )
    args_schema: type[BaseModel] = ChromaSearchInput

    def _run(self, query: str, k: int = 5) -> str:  # type: ignore[override]
        try:
            store = ChromaStore()
            hits = store.search_datasets(query, k=k)
        except Exception as e:
            return f"ERROR: ChromaDB unavailable ({e}). Run `make index` first."
        if not hits:
            return "No datasets found. Run `make index` to build the metadata index."
        lines: list[str] = []
        for i, h in enumerate(hits, 1):
            meta = h.get("metadata", {}) or {}
            lines.append(
                f"{i}. [{meta.get('vt_symbol', '?')}] {meta.get('path', '?')} "
                f"({meta.get('rows', '?')} rows, {meta.get('first_ts', '?')}..{meta.get('last_ts', '?')})\n"
                f"   summary: {h.get('document')}\n"
                f"   distance: {h.get('distance')}"
            )
        return "\n".join(lines)


class MemoryRecallInput(BaseModel):
    query: str
    role: str | None = None
    k: int = 5


class MemoryRecallTool(BaseTool):
    name: str = "memory_recall"
    description: str = "Retrieve past reflections and notes stored by other agents."
    args_schema: type[BaseModel] = MemoryRecallInput

    def _run(self, query: str, role: str | None = None, k: int = 5) -> str:  # type: ignore[override]
        try:
            store = ChromaStore()
            hits = store.recall(query, k=k, role=role)
        except Exception as e:
            return f"ERROR: {e}"
        if not hits:
            return "No relevant memories."
        return "\n".join(
            f"- [{(h.get('metadata') or {}).get('role', '?')}] {h.get('document')}"
            for h in hits
        )
