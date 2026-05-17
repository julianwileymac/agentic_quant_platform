"""Tagging enricher.

Asks the LLM for 3-8 short tags for the entity. Stored as
:class:`EntityAnnotation` (kind=``tag``) so users can filter the entity
browser by tag.
"""
from __future__ import annotations

import json
from typing import Any

from aqp.data.entities.enrichers.base import EntityEnricher
from aqp.data.entities.enrichers.description_enricher import DescriptionEnricher


_PROMPT = """You are a structured data assistant tagging entities in a financial knowledge graph.

Return one JSON object: {{ "tags": ["tag1", "tag2", ...] }}.

Rules:
- 3 to 8 tags per entity.
- Tags are short (1-3 lowercase tokens, no whitespace inside a tag, use underscores).
- Tag the entity's industry, sector, geography, regulatory status if relevant, and notable risks.

Entity:
{entity_json}
"""


class TaggingEnricher(EntityEnricher):
    """LLM-proposed tag suggestions, stored as one ``tag`` annotation."""

    name = "tagging"

    def enrich_one(self, entity: dict[str, Any]) -> dict[str, Any] | None:
        prompt = _PROMPT.format(
            entity_json=json.dumps(
                {
                    "kind": entity.get("kind"),
                    "name": entity.get("canonical_name"),
                    "attributes": entity.get("attributes") or {},
                },
                default=str,
            )
        )
        text = self._llm(prompt=prompt)
        if not text:
            return None
        parsed = DescriptionEnricher._parse_json(text)
        if not parsed:
            return None
        tags = [
            t.strip().lower().replace(" ", "_")
            for t in (parsed.get("tags") or [])
            if isinstance(t, str) and t.strip()
        ][:8]
        if not tags:
            return None
        return {
            "annotations": [
                {
                    "kind": "tag",
                    "content": ",".join(tags),
                    "model": self.model,
                    "provider": self.provider,
                    "author": "llm",
                    "confidence": 0.65,
                }
            ]
        }
