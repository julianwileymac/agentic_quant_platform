"""Entity-extraction + LLM-enrichment Dagster assets."""
from __future__ import annotations

from typing import Any

from dagster import AssetExecutionContext, asset

from aqp.dagster.assets.sources import (
    cfpb_complaints,
    fda_recalls,
    finance_database_equities,
    sec_filings,
    uspto_patents,
)


def _run_extract(
    *,
    flavor: str,
    iceberg_identifier: str,
    extractor_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from aqp.data.entities.extractors import EXTRACTOR_REGISTRY
    from aqp.data.iceberg_catalog import read_arrow

    extractor_cls = EXTRACTOR_REGISTRY[flavor]
    table = read_arrow(iceberg_identifier, limit=200_000)
    rows = table.to_pylist()
    extractor = extractor_cls(
        attach_iceberg_identifier=iceberg_identifier,
        source_dataset=iceberg_identifier,
        **(extractor_kwargs or {}),
    )
    return extractor.run(rows).to_dict()


@asset(
    deps=[cfpb_complaints],
    description="Extract company entities from CFPB complaints.",
    group_name="aqp_entities",
)
def cfpb_entities(context: AssetExecutionContext) -> dict[str, Any]:
    return _run_extract(
        flavor="regulatory",
        iceberg_identifier="aqp_cfpb.complaints",
        extractor_kwargs={"flavor": "cfpb"},
    )


@asset(
    deps=[fda_recalls],
    description="Extract product / company entities from FDA recalls.",
    group_name="aqp_entities",
)
def fda_entities(context: AssetExecutionContext) -> dict[str, Any]:
    return _run_extract(
        flavor="regulatory",
        iceberg_identifier="aqp_fda.recalls",
        extractor_kwargs={"flavor": "fda_recalls"},
    )


@asset(
    deps=[uspto_patents],
    description="Extract patent + assignee entities from USPTO patents.",
    group_name="aqp_entities",
)
def uspto_entities(context: AssetExecutionContext) -> dict[str, Any]:
    return _run_extract(
        flavor="regulatory",
        iceberg_identifier="aqp_uspto.patents",
        extractor_kwargs={"flavor": "uspto_patents"},
    )


@asset(
    deps=[sec_filings],
    description="Extract company entities from SEC filings index.",
    group_name="aqp_entities",
)
def sec_entities(context: AssetExecutionContext) -> dict[str, Any]:
    return _run_extract(
        flavor="filings",
        iceberg_identifier="aqp_sec.filings_index",
    )


@asset(
    deps=[finance_database_equities],
    description="Seed the unified entity registry from FinanceDatabase equities.",
    group_name="aqp_entities",
)
def finance_database_entities(context: AssetExecutionContext) -> dict[str, Any]:
    return _run_extract(
        flavor="finance_database",
        iceberg_identifier="aqp_finance_database.equities",
        extractor_kwargs={"asset_kind": "equities"},
    )


@asset(
    description="LLM-enrich the most-recent entities with descriptions + tags.",
    group_name="aqp_entities",
)
def entity_llm_enrichment(context: AssetExecutionContext) -> dict[str, Any]:
    from aqp.config import settings
    from aqp.data.entities.enrichers import DescriptionEnricher, TaggingEnricher
    from aqp.data.entities.registry import list_entities

    if not settings.entity_llm_enrichment_enabled:
        context.log.info("entity_llm_enrichment_enabled=False; skipping")
        return {"skipped": True}
    rows = list_entities(limit=200, canonical_only=True)
    ids = [r["id"] for r in rows]
    summary: dict[str, Any] = {}
    for cls in (DescriptionEnricher, TaggingEnricher):
        enricher = cls()
        summary[cls.__name__] = enricher.run(ids).to_dict()
    return summary


__all__ = [
    "cfpb_entities",
    "entity_llm_enrichment",
    "fda_entities",
    "finance_database_entities",
    "sec_entities",
    "uspto_entities",
]
