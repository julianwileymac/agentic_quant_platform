"""PDF parsers for the research-paper RAG corpus.

Three parser backends are exposed behind a single
:class:`BaseDocParser` interface plus a small selector chain:

- :class:`MarkerParser` — primary; uses the `marker-pdf` OSS package
  which preserves LaTeX-rich blocks in scientific PDFs.
- :class:`NougatParser` — fallback; Meta's academic-OCR transformer.
  Heavy weight but handles scanned PDFs that Marker can't reach.
- :class:`MathPixParser` — optional; commercial API, credential-gated
  via the AQP CredentialResolver. Set ``AQP_MATHPIX_APP_ID`` /
  ``AQP_MATHPIX_APP_KEY`` (or write them into the credentials file)
  to enable.

All three return a :class:`ParsedDoc` with normalised text blocks +
extracted LaTeX equations. Downstream chunking in the
``research_papers`` indexer treats math-bearing blocks specially
so equations and their surrounding variable definitions stay in the
same chunk.
"""
from __future__ import annotations

from aqp.rag.parsers.base import BaseDocParser, ParsedDoc, ParsedEquation
from aqp.rag.parsers.registry import (
    available_parsers,
    pick_parser,
    register_parser,
)

__all__ = [
    "BaseDocParser",
    "ParsedDoc",
    "ParsedEquation",
    "available_parsers",
    "pick_parser",
    "register_parser",
]
