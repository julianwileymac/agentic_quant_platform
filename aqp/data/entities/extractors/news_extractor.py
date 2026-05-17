"""Extract entities from GDELT news / event rows."""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from aqp.data.entities.extractors.base import EntityCandidate, EntityExtractor


def _str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


class NewsEntityExtractor(EntityExtractor):
    """Extract person / organization / location entities from GDELT GKG."""

    name = "news"
    extractor_id = "news.gdelt"

    def extract(self, rows: Iterable[Any]) -> Iterator[EntityCandidate]:
        for row in rows:
            data = row if isinstance(row, dict) else dict(row)
            persons = self._split_list(data.get("persons") or data.get("V2Persons"))
            organizations = self._split_list(
                data.get("organizations") or data.get("V2Organizations")
            )
            locations = self._split_list(
                data.get("locations") or data.get("V2Locations")
            )
            for name in persons[:50]:
                yield EntityCandidate(
                    kind="person",
                    canonical_name=name,
                    tags=["news", "gdelt"],
                    confidence=0.55,
                )
            for name in organizations[:50]:
                yield EntityCandidate(
                    kind="organization",
                    canonical_name=name,
                    tags=["news", "gdelt"],
                    confidence=0.55,
                )
            for name in locations[:50]:
                yield EntityCandidate(
                    kind="location",
                    canonical_name=name,
                    tags=["news", "gdelt"],
                    confidence=0.55,
                )

    @staticmethod
    def _split_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [_str(v) for v in value if _str(v)]  # type: ignore[list-item]
        text = str(value).strip()
        if not text:
            return []
        # GDELT uses ``;`` as the multi-value separator with ``,name#count`` shape.
        items: list[str] = []
        for chunk in text.split(";"):
            piece = chunk.split(",", 1)[0].strip()
            piece = piece.split("#", 1)[0].strip()
            if piece:
                items.append(piece)
        return items
