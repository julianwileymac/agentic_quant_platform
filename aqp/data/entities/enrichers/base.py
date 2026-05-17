"""Base class for entity enrichers.

All enrichers route LLM calls through
:func:`aqp.llm.providers.router.router_complete` per AGENTS.md hard
rule #2. None of them mutate the source dataset row — they emit
``EntityAnnotation``, alias-link, or relation-edge proposals via the
:class:`aqp.data.entities.EntityRegistry`.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from aqp.data.entities.registry import EntityRegistry, get_entity

logger = logging.getLogger(__name__)


@dataclass
class EnricherResult:
    """Aggregate counters returned by :meth:`EntityEnricher.run`."""

    enriched: int = 0
    annotations: int = 0
    relations: int = 0
    identifiers: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enriched": self.enriched,
            "annotations": self.annotations,
            "relations": self.relations,
            "identifiers": self.identifiers,
            "skipped": self.skipped,
            "errors": list(self.errors),
        }


class EntityEnricher:
    """Base class.

    Subclasses override :meth:`enrich_one` to return a structured dict
    that the framework persists as an :class:`EntityAnnotation`,
    relation, or alias.
    """

    name: str = "enricher"

    def __init__(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        registry: EntityRegistry | None = None,
    ) -> None:
        from aqp.config import settings

        self.provider = provider or settings.entity_llm_provider or settings.llm_provider
        self.model = model or settings.entity_llm_model or settings.llm_model
        self.temperature = float(temperature)
        self.max_tokens = int(max_tokens)
        self.registry = registry or EntityRegistry()
        self._llm_enabled = bool(settings.entity_llm_enrichment_enabled)

    # ------------------------------------------------------------------
    # Subclass hooks
    # ------------------------------------------------------------------

    def enrich_one(self, entity: dict[str, Any]) -> dict[str, Any] | None:
        """Return a delta dict for one entity.

        Shape::

            {
                "annotations": [{"kind": ..., "content": ..., "citations": [...]}, ...],
                "relations":   [{"predicate": ..., "object_id": ..., "confidence": ...}, ...],
                "identifiers": [{"scheme": ..., "value": ..., "source": ...}, ...],
            }
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(self, entity_ids: Iterable[str]) -> EnricherResult:
        result = EnricherResult()
        for entity_id in entity_ids:
            entity = get_entity(entity_id)
            if entity is None:
                result.skipped += 1
                continue
            try:
                delta = self.enrich_one(entity)
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"{self.name}:{entity_id}: {exc}")
                continue
            if not delta:
                result.skipped += 1
                continue
            result.enriched += 1
            for note in delta.get("annotations") or []:
                if self.registry.annotate(entity_id=entity_id, **note):
                    result.annotations += 1
            for rel in delta.get("relations") or []:
                if self.registry.add_relation(subject_id=entity_id, **rel):
                    result.relations += 1
            for ident in delta.get("identifiers") or []:
                if self.registry.link_identifier(entity_id=entity_id, **ident):
                    result.identifiers += 1
        return result

    # ------------------------------------------------------------------
    # LLM helper
    # ------------------------------------------------------------------

    def _llm(
        self,
        *,
        prompt: str,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> str | None:
        """Wrap router_complete; return assistant message text or None."""
        if not self._llm_enabled:
            logger.debug("entity LLM enrichment disabled (settings)")
            return None
        try:
            from aqp.llm.providers.router import router_complete
        except Exception as exc:  # noqa: BLE001
            logger.warning("router_complete unavailable: %s", exc)
            return None

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            result = router_complete(
                provider=self.provider,
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=max_tokens or self.max_tokens,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("router_complete failed: %s", exc)
            return None
        if result is None:
            return None
        text = getattr(result, "text", None) or getattr(result, "content", None)
        if not text and isinstance(result, dict):
            text = result.get("text") or result.get("content")
        return text


__all__ = ["EnricherResult", "EntityEnricher"]
