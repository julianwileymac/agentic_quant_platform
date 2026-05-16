"""Parser registry + selector chain.

Backends are registered eagerly on import. The selector picks the
first preferred-and-available backend so callers can override the
preference order (e.g. swap ``"mathpix"`` to the head when an API
key is available).
"""
from __future__ import annotations

import logging
from typing import Iterable

from aqp.rag.parsers.base import BaseDocParser

logger = logging.getLogger(__name__)


_PARSERS: dict[str, type[BaseDocParser]] = {}


def register_parser(cls: type[BaseDocParser]) -> type[BaseDocParser]:
    """Decorator: register ``cls`` under its ``name`` attribute."""
    if not cls.name or cls.name == "base":
        raise ValueError(f"parser {cls!r} must declare a non-default name")
    _PARSERS[cls.name] = cls
    return cls


def available_parsers() -> dict[str, type[BaseDocParser]]:
    """Return the subset of registered parsers whose deps are installed."""
    return {name: cls for name, cls in _PARSERS.items() if cls.available()}


def pick_parser(
    preference: Iterable[str] | str | None = None,
) -> BaseDocParser:
    """Return an instantiated parser following the preference chain.

    Defaults to ``[marker, mathpix, nougat, pypdf]`` so callers get
    the fastest math-aware backend that happens to be available.
    """
    if isinstance(preference, str):
        ordering = [preference]
    elif preference is not None:
        ordering = list(preference)
    else:
        ordering = ["marker", "mathpix", "nougat", "pypdf"]
    avail = available_parsers()
    for name in ordering:
        if name in avail:
            try:
                return avail[name]()
            except Exception as exc:  # noqa: BLE001
                logger.warning("parser %s failed to instantiate: %s", name, exc)
                continue
    raise RuntimeError(
        "no research-paper PDF parser available — install marker-pdf, nougat-ocr,"
        " pypdf, or set MathPix credentials. Try: pip install pypdf."
    )


# Side-effect imports so individual parsers can decorate themselves.
from aqp.rag.parsers.marker_parser import MarkerParser  # noqa: E402,F401
from aqp.rag.parsers.mathpix_parser import MathPixParser  # noqa: E402,F401
from aqp.rag.parsers.nougat_parser import NougatParser  # noqa: E402,F401
from aqp.rag.parsers.pypdf_parser import PyPDFParser  # noqa: E402,F401
