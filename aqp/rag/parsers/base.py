"""Base abstractions for the research-paper PDF parsers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ParsedEquation:
    """A single mathematical expression extracted from a PDF.

    ``latex`` is the canonical LaTeX form. ``inline`` flags inline
    vs display equations. ``section`` (optional) anchors the equation
    to a heading or section number.
    """

    latex: str
    inline: bool = False
    section: str | None = None
    page: int | None = None


@dataclass
class ParsedDoc:
    """Structured output of a single document parse.

    ``text_blocks`` is a list of plain-text sections in reading
    order. ``equations`` is a flat list of equations preserved as
    LaTeX (and inserted back into the text blocks via inline
    ``$<latex>$`` markers when the parser supports it). ``metadata``
    carries title / authors / institution / etc. extracted from the
    PDF where available.
    """

    text_blocks: list[str] = field(default_factory=list)
    equations: list[ParsedEquation] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    parser_name: str = "unknown"

    @property
    def equation_count(self) -> int:
        return len(self.equations)

    @property
    def contains_mathematics(self) -> bool:
        return self.equation_count > 0


class BaseDocParser(ABC):
    """ABC for PDF parsers.

    Implementations override :meth:`parse` and optionally
    :attr:`name` / :meth:`available`.
    """

    #: Short, lowercase identifier (``"marker"``, ``"nougat"``, …).
    name: str = "base"

    @classmethod
    def available(cls) -> bool:
        """Return True iff the parser's dependencies are importable."""
        return False

    @abstractmethod
    def parse(self, path: Path | str) -> ParsedDoc:
        """Parse a single PDF file and return a :class:`ParsedDoc`."""
        raise NotImplementedError
