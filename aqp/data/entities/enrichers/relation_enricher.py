"""Relation enricher.

Asks the LLM to propose ``(predicate, object_name)`` edges for an
entity. Returned proposals are matched against existing entities by
exact ``canonical_name`` lookup; un-matched targets are skipped (no
phantom rows).
"""
from __future__ import annotations

import json
from typing import Any

from aqp.data.entities.enrichers.base import EntityEnricher
from aqp.data.entities.enrichers.description_enricher import DescriptionEnricher
from aqp.data.entities.registry import search_entities


_PROMPT = """You are a structured data assistant proposing typed edges between entities in a financial knowledge graph.

Return one JSON object with this shape:

{{
  "relations": [
    {{
      "predicate": "<short snake_case predicate (e.g. competitor_of, subsidiary_of, manufactured_by)>",
      "object_name": "<canonical name of the target entity>",
      "object_kind": "<one of: company, person, security, product, drug, patent, location, organization>",
      "confidence": <float between 0 and 1>,
      "rationale": "<short explanation>"
    }}
  ]
}}

Limit to 5 high-confidence proposals. Skip if you have no high-confidence proposals.

Entity:
{entity_json}
"""


class RelationEnricher(EntityEnricher):
    """LLM-proposed entity relations."""

    name = "relation"

    def enrich_one(self, entity: dict[str, Any]) -> dict[str, Any] | None:
        prompt = _PROMPT.format(
            entity_json=json.dumps(
                {
                    "kind": entity.get("kind"),
                    "name": entity.get("canonical_name"),
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
        parsed = DescriptionEnricher._parse_json(text)
        if not parsed:
            return None
        relations: list[dict[str, Any]] = []
        for proposal in (parsed.get("relations") or [])[:5]:
            predicate = (proposal.get("predicate") or "").strip()
            object_name = (proposal.get("object_name") or "").strip()
            if not predicate or not object_name:
                continue
            object_kind = (proposal.get("object_kind") or "").strip() or None
            target_id = self._resolve_target(object_name, kind=object_kind)
            if not target_id:
                continue
            relations.append(
                {
                    "predicate": predicate,
                    "object_id": target_id,
                    "confidence": float(proposal.get("confidence") or 0.5),
                    "provenance": f"llm:{self.model}",
                    "properties": {
                        "rationale": proposal.get("rationale"),
                        "source": "llm",
                    },
                }
            )
        if not relations:
            return None
        return {"relations": relations}

    @staticmethod
    def _resolve_target(name: str, *, kind: str | None) -> str | None:
        hits = search_entities(name, kind=kind, limit=3)
        for hit in hits:
            if hit.get("canonical_name", "").strip().lower() == name.strip().lower():
                return hit["id"]
        if hits:
            return hits[0]["id"]
        return None
