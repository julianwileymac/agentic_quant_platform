"""Description enricher.

Asks the LLM for a 1-2 sentence factual description of the entity.
Stored as :class:`EntityAnnotation` with ``kind='description'``. Never
mutates the source dataset.
"""
from __future__ import annotations

import json
from typing import Any

from aqp.data.entities.enrichers.base import EntityEnricher


_PROMPT = """You are a structured data assistant helping describe entities in a financial knowledge graph.

Return one JSON object with exactly two fields:

{{
  "description": "<1-2 sentence factual description of the entity>",
  "citations": ["<short tag identifying source you relied on>", ...]
}}

If you do not have enough information, return {{ "description": null, "citations": [] }}.

Entity:
{entity_json}
"""


class DescriptionEnricher(EntityEnricher):
    """LLM-authored short description for an entity."""

    name = "description"

    def enrich_one(self, entity: dict[str, Any]) -> dict[str, Any] | None:
        prompt = _PROMPT.format(
            entity_json=json.dumps(
                {
                    "kind": entity.get("kind"),
                    "name": entity.get("canonical_name"),
                    "short_name": entity.get("short_name"),
                    "primary_identifier": entity.get("primary_identifier"),
                    "primary_identifier_scheme": entity.get(
                        "primary_identifier_scheme"
                    ),
                    "attributes": entity.get("attributes") or {},
                    "tags": entity.get("tags") or [],
                },
                default=str,
                indent=2,
            )
        )
        text = self._llm(prompt=prompt)
        if not text:
            return None
        parsed = self._parse_json(text)
        if not parsed or not parsed.get("description"):
            return None
        return {
            "annotations": [
                {
                    "kind": "description",
                    "content": str(parsed["description"]).strip(),
                    "model": self.model,
                    "provider": self.provider,
                    "citations": list(parsed.get("citations") or []),
                    "confidence": 0.7,
                    "author": "llm",
                }
            ]
        }

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any] | None:
        text = text.strip()
        if not text:
            return None
        if text.startswith("```"):
            # Strip code fence
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        try:
            return json.loads(text)
        except Exception:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except Exception:
                    return None
        return None
