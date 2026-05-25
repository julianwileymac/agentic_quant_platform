# Data flow

> Last refreshed: 2026-05-25 by aqp-index-curator (trigger: enterprise
> docs migration Phase 0 — every canonical-doc pointer in the table
> below rewritten from the legacy `aqp_docs/<slug>.md` shape to the
> Docusaurus `aqp_docs/docs/concepts/data/<slug>.md` shape per
> `CONCEPT_MAPPING` in `aqp_docs/scripts/migrate-content.py`).

| Concept | Canonical doc | Hard rules |
| --- | --- | --- |
| Iceberg catalog wrapper | [../../aqp_docs/docs/concepts/data/data-catalog.md](../../aqp_docs/docs/concepts/data/data-catalog.md) | AGENTS rule 3 |
| Medallion layers + business metadata | [../../aqp_docs/docs/concepts/data/data-layer-unification.md](../../aqp_docs/docs/concepts/data/data-layer-unification.md) | AGENTS rule 21 |
| DataMCP boundary | [../../aqp_docs/docs/concepts/data/data-mcp.md](../../aqp_docs/docs/concepts/data/data-mcp.md) | AGENTS rule 22 |
| Datasets catalog (typed `BaseDataset`) | [../../aqp_docs/docs/concepts/data/datasets-catalog.md](../../aqp_docs/docs/concepts/data/datasets-catalog.md) | AGENTS rule 29 |
| Metadata cache | [../../aqp_docs/docs/concepts/data/metadata-cache.md](../../aqp_docs/docs/concepts/data/metadata-cache.md) | AGENTS rule 29 |
| Discovery service | [../../aqp_docs/docs/concepts/data/data-discovery.md](../../aqp_docs/docs/concepts/data/data-discovery.md) | AGENTS rule 30 |
| Airbyte builder | [../../aqp_docs/docs/concepts/data/airbyte-builder.md](../../aqp_docs/docs/concepts/data/airbyte-builder.md) | AGENTS rule 31 |
| Dagster sandbox | [../../aqp_docs/docs/concepts/data/dagster-sandbox.md](../../aqp_docs/docs/concepts/data/dagster-sandbox.md) | AGENTS rule 32 |
| Hudi (additive to Iceberg) | [../../aqp_docs/docs/concepts/data/hudi.md](../../aqp_docs/docs/concepts/data/hudi.md) | AGENTS rule 46 |
| QuestDB time-series | [../../aqp_docs/docs/concepts/data/questdb.md](../../aqp_docs/docs/concepts/data/questdb.md) | additive |
| pgvector control plane | [../../aqp_docs/docs/concepts/data/pgvector-control-plane.md](../../aqp_docs/docs/concepts/data/pgvector-control-plane.md) | additive |
