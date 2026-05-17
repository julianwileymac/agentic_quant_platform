"""Embedding bridge for the codebase MCP — uses :class:`HierarchicalRAG`.

Per AGENTS rule 11, every embedding write goes through the
:class:`aqp.rag.HierarchicalRAG` facade into the new ``code_chunks``
corpus. The indexer chunks each file by symbol (lines of context per
class / function) and emits ``Chunk`` records the existing
``HierarchicalRAG.index_chunks`` API accepts.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from aqp.codebase.mcp.index.ast_index import Symbol

logger = logging.getLogger(__name__)


CODE_CHUNKS_CORPUS = "code_chunks"


@dataclass(slots=True)
class CodeChunk:
    file: str
    symbol_name: str
    symbol_kind: str
    start_line: int
    end_line: int
    text: str


def chunk_symbols(symbols: Iterable[Symbol], *, max_chars: int = 4000) -> list[CodeChunk]:
    """Chunk a symbol stream into roughly-sized snippets for indexing."""
    chunks: list[CodeChunk] = []
    for sym in symbols:
        if sym.kind in {"module", "import"}:
            # Skip module-level rows and import statements — the file
            # has its own catch-all chunk; imports are noise inside
            # semantic search.
            continue
        try:
            text = _read_lines(sym.file, sym.start_line, sym.end_line)
        except Exception:  # noqa: BLE001
            continue
        if not text:
            continue
        if len(text) > max_chars:
            text = text[: max_chars - 3] + "..."
        chunks.append(
            CodeChunk(
                file=sym.file,
                symbol_name=sym.name,
                symbol_kind=sym.kind,
                start_line=sym.start_line,
                end_line=sym.end_line,
                text=text,
            )
        )
    return chunks


def _read_lines(path: str, start_line: int, end_line: int) -> str:
    p = Path(path)
    if not p.is_file():
        return ""
    text = p.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    lo = max(0, int(start_line) - 1)
    hi = min(len(lines), int(end_line))
    return "\n".join(lines[lo:hi])


def upsert_chunks(chunks: Iterable[CodeChunk]) -> int:
    """Push the chunks through :class:`HierarchicalRAG.index_chunks`.

    Returns the number of chunks accepted by the RAG facade. Failures
    log and return ``0`` so the rest of the indexer can keep working.
    """
    try:
        from aqp.rag import HierarchicalRAG
        from aqp.rag.chunker import Chunk  # type: ignore
    except Exception as exc:  # noqa: BLE001
        logger.warning("HierarchicalRAG unavailable: %s", exc)
        return 0
    records: list[tuple[Chunk, dict[str, object]]] = []
    for c in chunks:
        records.append(
            (
                Chunk(
                    text=c.text,
                    metadata={
                        "corpus": CODE_CHUNKS_CORPUS,
                        "file": c.file,
                        "symbol_name": c.symbol_name,
                        "symbol_kind": c.symbol_kind,
                        "start_line": c.start_line,
                        "end_line": c.end_line,
                    },
                ),
                {"corpus": CODE_CHUNKS_CORPUS, "level": "l3"},
            )
        )
    if not records:
        return 0
    try:
        rag = HierarchicalRAG.get_default() if hasattr(HierarchicalRAG, "get_default") else HierarchicalRAG()
        return int(rag.index_chunks(CODE_CHUNKS_CORPUS, records, level="l3"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("HierarchicalRAG.index_chunks failed: %s", exc)
        return 0


__all__ = ["CODE_CHUNKS_CORPUS", "CodeChunk", "chunk_symbols", "upsert_chunks"]
