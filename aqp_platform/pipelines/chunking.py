"""Chunking strategies for document text.

Provides multiple strategies adapted from RAG_Techniques patterns:
 - Fixed-size with overlap (RecursiveCharacterTextSplitter equivalent)
 - Sliding window with contextual headers
 - Semantic boundary splitting
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Chunk:
    """A text chunk with provenance metadata."""

    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


def recursive_character_split(
    text: str,
    chunk_size: int = 800,
    chunk_overlap: int = 200,
    separators: list[str] | None = None,
) -> list[str]:
    """Split text recursively by trying separators in order.

    Mirrors LangChain's RecursiveCharacterTextSplitter logic without
    requiring the LangChain dependency at runtime.
    """
    if separators is None:
        separators = ["\n\n", "\n", ". ", " ", ""]

    if len(text) <= chunk_size:
        return [text] if text.strip() else []

    for sep in separators:
        if sep and sep in text:
            parts = text.split(sep)
            break
    else:
        parts = [text[i : i + chunk_size] for i in range(0, len(text), max(chunk_size - chunk_overlap, 1))]
        return [p for p in parts if p.strip()]

    chunks: list[str] = []
    current = ""
    for part in parts:
        candidate = (current + sep + part) if current else part
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current.strip():
                chunks.append(current.strip())
            current = part

    if current.strip():
        chunks.append(current.strip())

    final: list[str] = []
    for chunk in chunks:
        if len(chunk) > chunk_size:
            remaining_seps = separators[separators.index(sep) + 1 :] if sep in separators else separators[1:]
            final.extend(
                recursive_character_split(
                    chunk,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                    separators=remaining_seps,
                )
            )
        else:
            final.append(chunk)

    if chunk_overlap > 0 and len(final) > 1:
        overlapped: list[str] = [final[0]]
        for i in range(1, len(final)):
            prev_tail = final[i - 1][-chunk_overlap:]
            merged = prev_tail + " " + final[i]
            if len(merged) <= chunk_size:
                overlapped.append(merged)
            else:
                overlapped.append(final[i])
        return overlapped

    return final


def sliding_window_with_context(
    text: str,
    chunk_size: int = 800,
    window_overlap: int = 200,
    header: str = "",
) -> list[Chunk]:
    """Sliding-window chunking that prepends a contextual header to each
    chunk.  Inspired by the 'contextual_chunk_headers' RAG technique.
    """
    raw_chunks = recursive_character_split(text, chunk_size=chunk_size, chunk_overlap=window_overlap)
    results: list[Chunk] = []
    for idx, raw in enumerate(raw_chunks):
        prefixed = f"{header}\n\n{raw}" if header else raw
        results.append(
            Chunk(
                text=prefixed,
                metadata={"chunk_index": idx, "strategy": "sliding_window_context"},
            )
        )
    return results


_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def sentence_split(text: str) -> list[str]:
    """Split text into sentences."""
    return [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]


def semantic_boundary_split(
    text: str,
    max_chunk_size: int = 1200,
    min_chunk_size: int = 100,
) -> list[Chunk]:
    """Split by semantic boundaries (paragraphs first, then sentences).

    Groups adjacent sentences into chunks that respect size limits while
    preferring paragraph boundaries.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[Chunk] = []
    current = ""

    for para in paragraphs:
        if len(para) > max_chunk_size:
            if current.strip():
                chunks.append(Chunk(text=current.strip(), metadata={"strategy": "semantic_boundary"}))
                current = ""
            sentences = sentence_split(para)
            for sent in sentences:
                if len(current) + len(sent) + 1 > max_chunk_size:
                    if current.strip():
                        chunks.append(Chunk(text=current.strip(), metadata={"strategy": "semantic_boundary"}))
                    current = sent
                else:
                    current = f"{current} {sent}" if current else sent
        elif len(current) + len(para) + 2 > max_chunk_size:
            if current.strip():
                chunks.append(Chunk(text=current.strip(), metadata={"strategy": "semantic_boundary"}))
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para

    if current.strip() and len(current.strip()) >= min_chunk_size:
        chunks.append(Chunk(text=current.strip(), metadata={"strategy": "semantic_boundary"}))
    elif current.strip() and chunks:
        chunks[-1] = Chunk(
            text=chunks[-1].text + "\n\n" + current.strip(),
            metadata=chunks[-1].metadata,
        )

    for idx, chunk in enumerate(chunks):
        chunk.metadata["chunk_index"] = idx

    return chunks


def chunk_documents(
    texts: list[str],
    strategy: str = "recursive",
    chunk_size: int = 800,
    chunk_overlap: int = 200,
    header: str = "",
) -> list[Chunk]:
    """Unified entry point for chunking a list of texts.

    Supported strategies: "recursive", "sliding_window", "semantic".
    """
    all_chunks: list[Chunk] = []

    for text in texts:
        if strategy == "sliding_window":
            all_chunks.extend(
                sliding_window_with_context(text, chunk_size=chunk_size, window_overlap=chunk_overlap, header=header)
            )
        elif strategy == "semantic":
            all_chunks.extend(semantic_boundary_split(text, max_chunk_size=chunk_size))
        else:
            raw = recursive_character_split(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
            for idx, r in enumerate(raw):
                all_chunks.append(Chunk(text=r, metadata={"chunk_index": idx, "strategy": "recursive"}))

    for global_idx, chunk in enumerate(all_chunks):
        chunk.metadata["global_index"] = global_idx

    return all_chunks
