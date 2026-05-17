"""LLM-driven entity enrichers (rule #2: route through router_complete)."""
from __future__ import annotations

from aqp.data.entities.enrichers.base import EnricherResult, EntityEnricher
from aqp.data.entities.enrichers.dedup_enricher import DedupEnricher
from aqp.data.entities.enrichers.description_enricher import DescriptionEnricher
from aqp.data.entities.enrichers.relation_enricher import RelationEnricher
from aqp.data.entities.enrichers.tagging_enricher import TaggingEnricher

ENRICHER_REGISTRY: dict[str, type[EntityEnricher]] = {
    "description": DescriptionEnricher,
    "relation": RelationEnricher,
    "dedup": DedupEnricher,
    "tagging": TaggingEnricher,
}


def get_enricher(name: str) -> type[EntityEnricher]:
    if name not in ENRICHER_REGISTRY:
        raise KeyError(f"unknown enricher {name!r}")
    return ENRICHER_REGISTRY[name]


__all__ = [
    "DedupEnricher",
    "DescriptionEnricher",
    "ENRICHER_REGISTRY",
    "EnricherResult",
    "EntityEnricher",
    "RelationEnricher",
    "TaggingEnricher",
    "get_enricher",
]
