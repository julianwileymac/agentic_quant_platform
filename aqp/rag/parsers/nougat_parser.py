"""Nougat-based PDF parser (academic-OCR fallback)."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from aqp.rag.parsers.base import BaseDocParser, ParsedDoc, ParsedEquation

logger = logging.getLogger(__name__)


_DISPLAY_RE = re.compile(r"\\\[(.+?)\\\]", re.DOTALL)
_INLINE_RE = re.compile(r"\\\((.+?)\\\)", re.DOTALL)


class NougatParser(BaseDocParser):
    """Nougat academic-OCR parser.

    Nougat (Meta AI, 2023) is a transformer trained on arXiv PDFs;
    it produces markdown with LaTeX preserved. We invoke it via the
    `nougat` CLI when present.
    """

    name = "nougat"

    @classmethod
    def available(cls) -> bool:
        try:
            import nougat  # type: ignore[import-not-found]  # noqa: F401

            return True
        except Exception:  # noqa: BLE001
            return False

    def parse(self, path: Path | str) -> ParsedDoc:
        import subprocess  # noqa: S404 - external CLI invocation

        path = Path(path)
        cmd = ["nougat", "--no-skipping", str(path), "--out", "-"]
        try:
            proc = subprocess.run(  # noqa: S603
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=600,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("nougat CLI failed on %s: %s", path, exc)
            raise

        text = proc.stdout
        equations: list[ParsedEquation] = []
        for match in _DISPLAY_RE.finditer(text):
            equations.append(ParsedEquation(latex=match.group(1).strip(), inline=False))
        for match in _INLINE_RE.finditer(text):
            equations.append(ParsedEquation(latex=match.group(1).strip(), inline=True))
        blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
        return ParsedDoc(
            text_blocks=blocks,
            equations=equations,
            metadata={"source": "nougat"},
            parser_name=self.name,
        )


from aqp.rag.parsers.registry import register_parser  # noqa: E402

register_parser(NougatParser)
