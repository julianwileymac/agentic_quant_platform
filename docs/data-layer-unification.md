# Data Layer Unification

> Top-level entry point for the unified AQP data layer. Read this first
> when working on anything that touches catalog, pipelines, products, or
> the MCP tool surface.

The data layer unification gives AQP one authoritative way to:

1. **Land** raw bytes into the Lakehouse (Bronze namespaces)
2. **Normalise** them via registered Strategy classes (Silver namespaces)
3. **Aggregate** them into entity-centric data products (Gold namespaces)
4. **Catalog** technical + business metadata + lineage on every write
5. **Expose** all of the above through the DataMCP tool surface — same
   tool catalog, two transports (in-process bridge for AgentRuntime +
   FastAPI / stdio for external clients)
6. **Control** the whole thing from the unified Data Hub UI at
   [/data/hub](../webui/app/(shell)/data/hub/page.tsx)

## Core building blocks

| Concern | Module | Doc |
| --- | --- | --- |
| Iceberg writes | [aqp/data/iceberg_catalog.py](../aqp/data/iceberg_catalog.py) | [docs/data-catalog.md](data-catalog.md) |
| Active metadata | [aqp/data/catalog/active_metadata.py](../aqp/data/catalog/active_metadata.py) | this file |
| Lineage tracking | [aqp/data/catalog/lineage.py](../aqp/data/catalog/lineage.py) | this file |
| Pipelines | [aqp/data/engine/](../aqp/data/engine/) | [docs/data-engine.md](data-engine.md) |
| Normalization | [aqp/data/normalization/](../aqp/data/normalization/) | this file |
| Data products | [aqp/data/products/](../aqp/data/products/) | [docs/data-products.md](data-products.md) |
| DataMCP tools | [aqp/data/mcp/](../aqp/data/mcp/) | [docs/data-mcp.md](data-mcp.md) |
| Unified UI | [/data/hub](../webui/app/(shell)/data/hub/page.tsx) | this file |

## Medallion architecture

Three layers, each pinned to a namespace prefix:

| Layer | Namespace prefix | What lives here |
| --- | --- | --- |
| Bronze | `aqp_bronze_*` | Raw, append-only journal as it lands from a fetcher |
| Silver | `aqp_silver_*` | Normalised, deduped, schema-validated rows |
| Gold | `aqp_gold_*` | Feature sets + entity-centric data products |

`iceberg_catalog.append_arrow(..., medallion_layer="silver")` validates
that the namespace prefix matches the layer. New tables must declare a
layer; legacy tables stay nullable until a fresh write touches them.

## Active metadata contract

Every Iceberg table that an agent touches MUST have a
`DatasetCatalog` row with:

- `medallion_layer` (`bronze` / `silver` / `gold`)
- `business_metadata.data_owner` (string, required)
- `business_metadata.semantic_definition` (string, required)
- `business_metadata.reliability_score` (float 0..1, optional)
- `business_metadata.sla_class` (eg. `tier-1-realtime`, optional)
- `data_contract_json.columns` (list of column-level contracts)

Use the helper:

```python
from aqp.data.catalog import register_dataset, BusinessMetadata

register_dataset(
    "aqp_silver_alpha_vantage.daily_bars",
    medallion_layer="silver",
    business_metadata=BusinessMetadata(
        data_owner="data-team",
        semantic_definition="Daily OHLCV bars normalised against UTC.",
        reliability_score=0.95,
        sla_class="tier-2-eod",
        domain="market.bars",
    ),
)
```

…or attach a `@dataset(...)` decorator to your fetcher / sink class so
the upsert fires on first append.

## First-class lineage

Every material data motion writes one row to `data_lineage_events`
through `LineageWriter`:

- `iceberg_catalog.append_arrow` -> `transform_kind="iceberg_append"`
- engine `LocalExecutor.execute` -> `transform_kind="materialize"`
- `materialise_node_spec` -> `transform_kind="sink"`
- `DbtRunnerService.invoke` -> `transform_kind="dbt"`
- `airbyte _finish_run_row` -> `transform_kind="airbyte"`
- DataMCP tool invocation -> `transform_kind="mcp_tool"`
- normalization detects new column -> `transform_kind="schema_drift"`

Read the graph through `/data-control/lineage` (UI) or via the
`data.catalog.lineage` MCP tool (agents).

## DataMCP tool surface

A single registry, two transports:

```
DATA_MCP_TOOLS  ->  TOOL_REGISTRY bridge      ->  AgentRuntime (LiteLLM tools=)
              \->  /mcp/data (FastAPI HTTP)  ->  Cursor / Claude Desktop
              \->  aqp-data-mcp (stdio)      ->  any MCP-aware client
```

Add a tool: subclass `DataMCPTool`, decorate with
`@register_data_mcp_tool`, and the bridge auto-installs it into
`TOOL_REGISTRY` on next process boot.

## Cross-cutting rules

Two new hard rules in [.cursor/rules/aqp.mdc](../.cursor/rules/aqp.mdc):

1. All Iceberg writes that land in a tracked dataset MUST pass
   `medallion_layer` and the active-metadata payload.
2. All agent reads of catalog / datasets / entities / pipelines MUST
   go through `DATA_MCP_TOOLS`. Never query Postgres directly from
   inside an agent body.

See [AGENTS.md](../AGENTS.md) for the full rule set.
