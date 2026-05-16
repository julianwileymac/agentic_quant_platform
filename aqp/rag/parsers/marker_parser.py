"""Marker-based PDF parser (primary).

Marker (https://github.com/VikParuchuri/marker) is an OSS PDF parser
optimised for scientific papers. It preserves LaTeX-ish math blocks
inline in the markdown it emits, which the indexer can splice into
plain-text chunks without losing the math semantics.

The parser is lazy-imported because Marker is a heavyweight
dependency (~3GB of model weights). When unavailable, the registry
falls back to MathPix / Nougat / PyPDF.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from aqp.rag.parsers.base import BaseDocParser, ParsedDoc, ParsedEquation

logger = logging.getLogger(__name__)

_MATH_BLOCK_RE = re.compile(r"\$\$(.+?)\$\$|\\\[(.+?)\\\]", re.DOTALL)
_MATH_INLINE_RE = re.compile(r"\$(.+?)\$|\\\((.+?)\\\)", re.DOTALL)


def _split_blocks(markdown: str) -> list[str]:
    """Split a markdown blob into reading-order text blocks."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", markdown)]
    return [b for b in blocks if b]


class MarkerParser(BaseDocParser):
    """Marker-based PDF parser."""

    name = "marker"

    @classmethod
    def available(cls) -> bool:
        try:
            import marker  # type: ignore[import-not-found]  # noqa: F401

            return True
        except Exception:  # noqa: BLE001
            return False

    def parse(self, path: Path | str) -> ParsedDoc:
        from marker.convert import convert_single_pdf  # type: ignore[import-not-found]
        from marker.models import load_all_models  # type: ignore[import-not-found]

        path = Path(path)
        models = load_all_models()
        try:
            full_text, _images, _stats = convert_single_pdf(str(path), models)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Marker failed on %s: %s", path, exc)
            raise

        equations: list[ParsedEquation] = []
        for match in _MATH_BLOCK_RE.finditer(full_text):
            latex = (match.group(1) or match.group(2) or "").strip()
            if latex:
                equations.append(ParsedEquation(latex=latex, inline=False))
        for match in _MATH_INLINE_RE.finditer(full_text):
            latex = (match.group(1) or match.group(2) or "").strip()
            if latex:
                equations.append(ParsedEquation(latex=latex, inline=True))
        blocks = _split_blocks(full_text)
        return ParsedDoc(
            text_blocks=blocks,
            equations=equations,
            metadata={"source": "marker"},
            parser_name=self.name,
        )


# Side-effect: register on import.
from aqp.rag.parsers.registry import register_parser  # noqa: E402

register_parser(MarkerParser)
