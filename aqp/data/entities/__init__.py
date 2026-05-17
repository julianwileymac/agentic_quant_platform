"""Unified entity registry: companies, products, drugs, patents, persons, locations.

Two halves:

- :mod:`aqp.data.entities.registry` — typed CRUD facade backed by
  :mod:`aqp.persistence.models_entity_registry`.
- :mod:`aqp.data.entities.extractors` — Arrow → entity-row pipelines
  for every dataset family that ships an extractor.
- :mod:`aqp.data.entities.enrichers` — LLM-augmented description /
  relation / dedup / tagging passes that never mutate raw data.
"""
from __future__ import annotations

from aqp.data.entities.registry import (
    EntityRegistry,
    add_entity_relation,
    attach_entity_to_dataset,
    entity_graph,
    get_entity,
    link_entity_identifier,
    list_entities,
    search_entities,
    upsert_entity,
)

__all__ = [
    "EntityRegistry",
    "add_entity_relation",
    "attach_entity_to_dataset",
    "entity_graph",
    "get_entity",
    "link_entity_identifier",
    "list_entities",
    "search_entities",
    "upsert_entity",
]
