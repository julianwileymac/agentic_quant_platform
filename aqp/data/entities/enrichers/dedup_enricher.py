"""Dedup enricher.

Looks for duplicate entities (same kind + similar canonical name) and
proposes ``alias_of`` relations / sets the older row's
``is_canonical`` to false. Uses the LLM (when enabled) to break ties
on borderline matches; otherwise falls back to a deterministic
string-similarity threshold from
:class:`aqp.config.Settings.entity_dedup_similarity_threshold`.
"""
from __future__ import annotations

import json
from difflib import SequenceMatcher
from typing import Any

from aqp.data.entities.enrichers.base import EntityEnricher
from aqp.data.entities.enrichers.description_enricher import DescriptionEnricher
from aqp.data.entities.registry import search_entities


_PROMPT = """You are deduplicating entities in a financial knowledge graph.

The entity below has these candidate duplicates. For each, return whether they are the same real-world entity.

Return JSON: {{ "matches": [ {{ "id": "<other_id>", "is_match": true|false, "rationale": "..." }} ] }}

Entity:
{entity_json}

Candidates:
{candidates_json}
"""


class DedupEnricher(EntityEnricher):
    """Propose alias relations for likely duplicate entities."""

    name = "dedup"

    def enrich_one(self, entity: dict[str, Any]) -> dict[str, Any] | None:
        from aqp.config import settings

        candidates = search_entities(
            entity.get("canonical_name") or "",
            kind=entity.get("kind"),
            limit=10,
        )
        candidates = [c for c in candidates if c.get("id") != entity.get("id")]
        if not candidates:
            return None

        threshold = float(settings.entity_dedup_similarity_threshold or 0.85)
        deterministic = self._deterministic_matches(entity, candidates, threshold)
        llm_matches = self._llm_matches(entity, candidates) if self._llm_enabled else []

        merged: dict[str, dict[str, Any]] = {}
        for entry in deterministic + llm_matches:
            merged[entry["id"]] = entry

        relations: list[dict[str, Any]] = []
        for entry in merged.values():
            if not entry.get("is_match"):
                continue
            relations.append(
                {
                    "predicate": "alias_of",
                    "object_id": entry["id"],
                    "confidence": float(entry.get("confidence") or 0.85),
                    "provenance": entry.get("provenance") or "dedup",
                    "properties": {
                        "rationale": entry.get("rationale"),
                    },
                }
            )
        if not relations:
            return None
        return {"relations": relations}

    @staticmethod
    def _deterministic_matches(
        entity: dict[str, Any],
        candidates: list[dict[str, Any]],
        threshold: float,
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        name = (entity.get("canonical_name") or "").strip().lower()
        if not name:
            return out
        for candidate in candidates:
            other = (candidate.get("canonical_name") or "").strip().lower()
            if not other:
                continue
            score = SequenceMatcher(None, name, other).ratio()
            if score >= threshold:
                out.append(
                    {
                        "id": candidate["id"],
                        "is_match": True,
                        "confidence": score,
                        "rationale": f"string similarity {score:.2f}",
                        "provenance": "dedup:deterministic",
                    }
                )
        return out

    def _llm_matches(
        self,
        entity: dict[str, Any],
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        prompt = _PROMPT.format(
            entity_json=json.dumps(
                {"id": entity["id"], "name": entity["canonical_name"]},
                default=str,
            ),
            candidates_json=json.dumps(
                [
                    {
                        "id": c["id"],
                        "name": c["canonical_name"],
                        "attributes": c.get("attributes"),
                    }
                    for c in candidates
                ],
                default=str,
            ),
        )
        text = self._llm(prompt=prompt)
        if not text:
            return []
        parsed = DescriptionEnricher._parse_json(text)
        if not parsed:
            return []
        return [
            {
                "id": entry.get("id"),
                "is_match": bool(entry.get("is_match")),
                "rationale": entry.get("rationale"),
                "confidence": 0.9,
                "provenance": f"dedup:llm:{self.model}",
            }
            for entry in (parsed.get("matches") or [])
            if entry.get("id")
        ]
