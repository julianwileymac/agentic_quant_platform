"""Text chunkers used by the RAG indexers.

Three strategies are exposed (kept dependency-free):

- :func:`token_chunks` — fixed token-budget windows with overlap (FinGPT
  ``_chunk_text`` style; uses whitespace tokens when no tokenizer is
  available, ``tiktoken`` cl100k when it is).
- :func:`section_chunks` — split on heading patterns (``# H1``, ``##
  H2``, all-caps lines), keep the heading with the body.
- :func:`semantic_chunks` — sentence packing within a token budget.

All chunkers return a list of ``Chunk`` records keeping per-chunk
metadata (heading, char range, token count) so downstream consumers can
trace back to the source.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


_HEADING_RE = re.compile(r"^(#{1,6})\s*(.+?)\s*$", re.MULTILINE)
_ALL_CAPS_HEADING_RE = re.compile(r"^([A-Z][A-Z0-9 ,&\-/]{4,})\s*$", re.MULTILINE)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"\(])")


@dataclass
class Chunk:
    """Single chunk produced by a chunker."""

    text: str
    index: int
    start: int = 0
    end: int = 0
    token_count: int = 0
    heading: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def _tokens_of(text: str) -> list[str]:
    """Cheap approximate tokenization (fall back from ``tiktoken``)."""
    try:
        import tiktoken  # type: ignore[import-not-found]

        enc = tiktoken.get_encoding("cl100k_base")
        return [str(t) for t in enc.encode(text or "")]
    except Exception:  # pragma: no cover
        return (text or "").split()


def _detokenize(tokens: list[str]) -> str:
    return " ".join(tokens)


def token_chunks(
    text: str,
    *,
    max_tokens: int = 512,
    overlap: int = 64,
    heading: str = "",
) -> list[Chunk]:
    """Split ``text`` into fixed token windows with overlap."""
    text = (text or "").strip()
    if not text:
        return []
    if max_tokens <= 0:
        raise ValueError("max_tokens must be > 0")
    overlap = max(0, min(overlap, max_tokens - 1))
    tokens = _tokens_of(text)
    if not tokens:
        return []
    chunks: list[Chunk] = []
    step = max_tokens - overlap
    cursor = 0
    idx = 0
    while cursor < len(tokens):
        window = tokens[cursor : cursor + max_tokens]
        chunk_text = _detokenize(window)
        chunks.append(
            Chunk(
                text=chunk_text,
                index=idx,
                start=cursor,
                end=cursor + len(window),
                token_count=len(window),
                heading=heading,
            )
        )
        idx += 1
        if cursor + max_tokens >= len(tokens):
            break
        cursor += step
    return chunks


def section_chunks(
    text: str,
    *,
    max_tokens: int = 512,
    overlap: int = 64,
) -> list[Chunk]:
    """Split on Markdown headings (``#``..``######``) or all-caps lines."""
    text = (text or "").strip()
    if not text:
        return []
    sections = _split_on_headings(text)
    out: list[Chunk] = []
    idx = 0
    for heading, body in sections:
        for c in token_chunks(
            body, max_tokens=max_tokens, overlap=overlap, heading=heading
        ):
            c.index = idx
            out.append(c)
            idx += 1
    return out


def _split_on_headings(text: str) -> list[tuple[str, str]]:
    matches: list[tuple[int, str]] = []
    for m in _HEADING_RE.finditer(text):
        matches.append((m.start(), m.group(2).strip()))
    for m in _ALL_CAPS_HEADING_RE.finditer(text):
        matches.append((m.start(), m.group(1).strip().title()))
    matches.sort(key=lambda p: p[0])
    if not matches:
        return [("", text)]
    sections: list[tuple[str, str]] = []
    if matches[0][0] > 0:
        sections.append(("", text[: matches[0][0]].strip()))
    for i, (start, heading) in enumerate(matches):
        end = matches[i + 1][0] if (i + 1) < len(matches) else len(text)
        body = text[start:end]
        # strip the heading line itself from the body
        nl = body.find("\n")
        body = body[nl + 1 :] if nl >= 0 else ""
        body = body.strip()
        if body:
            sections.append((heading, body))
    return sections


def semantic_chunks(
    text: str,
    *,
    max_tokens: int = 384,
    heading: str = "",
) -> list[Chunk]:
    """Pack consecutive sentences up to ``max_tokens`` per chunk.

    Avoids slicing through sentence boundaries (kinder to retrievers).
    """
    text = (text or "").strip()
    if not text:
        return []
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    if not sentences:
        return []
    chunks: list[Chunk] = []
    current: list[str] = []
    current_tokens = 0
    idx = 0
    for sent in sentences:
        n = len(_tokens_of(sent))
        if current and current_tokens + n > max_tokens:
            chunk_text = " ".join(current)
            chunks.append(
                Chunk(
                    text=chunk_text,
                    index=idx,
                    token_count=current_tokens,
                    heading=heading,
                )
            )
            idx += 1
            current = []
            current_tokens = 0
        current.append(sent)
        current_tokens += n
    if current:
        chunks.append(
            Chunk(
                text=" ".join(current),
                index=idx,
                token_count=current_tokens,
                heading=heading,
            )
        )
    return chunks


def chunks_from_records(
    records: Iterable[dict[str, Any]],
    *,
    text_field: str = "text",
    max_tokens: int = 384,
    overlap: int = 32,
    strategy: str = "token",
) -> list[tuple[dict[str, Any], Chunk]]:
    """Helper used by indexers — yield ``(record, chunk)`` pairs."""
    out: list[tuple[dict[str, Any], Chunk]] = []
    for rec in records:
        text = (rec.get(text_field) or "").strip()
        if not text:
            continue
        if strategy == "section":
            cs = section_chunks(text, max_tokens=max_tokens, overlap=overlap)
        elif strategy == "semantic":
            cs = semantic_chunks(text, max_tokens=max_tokens)
        else:
            cs = token_chunks(text, max_tokens=max_tokens, overlap=overlap)
        for c in cs:
            out.append((rec, c))
    return out


__all__ = [
    "Chunk",
    "chunks_from_records",
    "section_chunks",
    "semantic_chunks",
    "token_chunks",
]
