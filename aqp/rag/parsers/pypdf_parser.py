"""PyPDF text-only fallback parser.

Used when none of the math-aware backends (Marker / Nougat / MathPix)
are available. Returns plain text only — equations are not preserved
as LaTeX, but the indexer can still ingest the prose. Useful in test
fixtures and for non-mathematical research notes.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from aqp.rag.parsers.base import BaseDocParser, ParsedDoc

logger = logging.getLogger(__name__)


class PyPDFParser(BaseDocParser):
    name = "pypdf"

    @classmethod
    def available(cls) -> bool:
        try:
            import pypdf  # type: ignore[import-not-found]  # noqa: F401

            return True
        except Exception:  # noqa: BLE001
            try:
                import PyPDF2  # type: ignore[import-not-found]  # noqa: F401

                return True
            except Exception:  # noqa: BLE001
                return False

    def parse(self, path: Path | str) -> ParsedDoc:
        path = Path(path)
        try:
            from pypdf import PdfReader  # type: ignore[import-not-found]
        except Exception:  # noqa: BLE001
            from PyPDF2 import PdfReader  # type: ignore[import-not-found]
        reader = PdfReader(str(path))
        pages = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception as exc:  # noqa: BLE001
                logger.debug("pypdf page extraction failed: %s", exc)
                pages.append("")
        text = "\n\n".join(pages)
        blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
        meta: dict[str, object] = {}
        try:
            info = reader.metadata or {}
            for key in ("/Title", "/Author", "/Producer"):
                if key in info:
                    meta[key.lstrip("/").lower()] = info[key]
        except Exception:  # noqa: BLE001
            pass
        return ParsedDoc(
            text_blocks=blocks,
            equations=[],
            metadata=meta,
            parser_name=self.name,
        )


from aqp.rag.parsers.registry import register_parser  # noqa: E402

register_parser(PyPDFParser)
