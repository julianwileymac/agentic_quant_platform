# Entity-Centric Data Products

> Pre-aggregated, read-only views over Silver / Gold tables. Each
> product hands an LLM agent a *Minimum Viable Data* shape for one
> business entity in a single call.

## Why entity-centric?

Without these wrappers, an agent that wants to "reason about AAPL"
would need to:

1. Query `Instrument` for the polymorphic equity record
2. Join `IdentifierLink` to find aliases
3. Read recent bars from `aqp_silver_alpha_vantage.daily_bars`
4. Look up fundamentals + ratios + news + regulatory mentions
5. Reconstruct provenance + lineage manually

The data product collapses all of that into one synchronous call:

```python
from aqp.data.products import EquityEntity

product = EquityEntity("AAPL.NASDAQ")
context = product.to_context_pack(max_tokens=4000)
```

The returned envelope carries the payload, provenance, quality, and
lineage breadcrumbs.

## Available products

| Product | Entity id | What it aggregates |
| --- | --- | --- |
| `EquityEntity` | `vt_symbol` | Instrument + identifiers + bars snapshot + fundamentals + ratios + news + regulatory counts |
| `OptionChainEntity` | `vt_symbol` | Latest `OptionChainSnapshot` + `OptionSeries` chain (bounded by `max_strikes`) |
| `MacroSeriesEntity` | series id (eg. `FRED:DGS10`) | `EconomicSeriesRow` metadata + N most recent observations |
| `RegulatoryEntity` | `vt_symbol` | CFPB complaints, FDA applications/recalls/adverse events, USPTO patents/trademarks/assignments |
| `PortfolioEntity` | portfolio id | Net positions, recent fills, latest ledger snapshot |
| `InstrumentGraphProduct` | root `vt_symbol` | BFS walk of the entity graph (instruments + issuers + identifier links) |

## Context pack envelope

Every `to_context_pack()` returns:

```jsonc
{
  "product_kind": "equity",
  "entity_id": "AAPL.NASDAQ",
  "as_of": "2026-05-08T19:13:00.000Z",
  "payload": {
    "instrument": { ... },
    "identifiers": [...],
    "fundamentals": [...],
    "ratios": [...],
    "news": [...],
    "regulatory": { "cfpb_complaints": 12, ... },
    "snapshot": { "rows": 30, "last_close": 187.4, ... }
  },
  "provenance": {
    "data_sources": ["alpha_vantage", "sec"],
    "dataset_versions": [],
    "upstream_iceberg_tables": ["aqp_silver_alpha_vantage.daily_bars"],
    "last_updated": "..."
  },
  "quality": {
    "reliability_score": 0.95,
    "completeness": 0.93,
    "freshness_seconds": 3600.0,
    "breakdown": { "bars_rows": 28, "lookback_days": 30 }
  },
  "lineage": [
    { "transform_kind": "data_product_load", "summary": "...", "timestamp": "..." }
  ]
}
```

When `max_tokens` is provided, sections beyond the budget are dropped
(see `_enforce_token_budget` in
[aqp/data/products/base.py](../aqp/data/products/base.py)) and listed
under `truncated_sections` so the agent knows what was cut.

## REST surface

Each product is exposed via [aqp/api/routes/data_entities.py](../aqp/api/routes/data_entities.py):

| Path | Product |
| --- | --- |
| `GET /data/entities/{vt_symbol}` | `EquityEntity` |
| `GET /data/entities/{vt_symbol}/option-chain` | `OptionChainEntity` |
| `GET /data/entities/macro/{series_id}` | `MacroSeriesEntity` |
| `GET /data/entities/regulatory/{vt_symbol}` | `RegulatoryEntity` |
| `GET /data/entities/portfolio/{portfolio_id}` | `PortfolioEntity` |
| `GET /data/entities/graph/{root_vt_symbol}` | `InstrumentGraphProduct` |

The unified Data Hub UI's "Entities" tab consumes these directly.

## DataMCP tools

Every product is also exposed as a `DataMCPTool` so agents can pull
the same shape via the in-process or external MCP transport:

- `data.entities.equity`
- `data.entities.option_chain`
- `data.entities.macro_series`
- `data.entities.regulatory`
- `data.entities.portfolio`
- `data.entities.instrument_graph`

See [aqp_docs/data-mcp.md](data-mcp.md) for tool catalog details.

## Adding a product

1. Subclass `BaseDataProduct` in `aqp/data/products/<your_kind>.py`
2. Set `product_kind = "your_kind"` (snake_case)
3. Implement `load()` — populate `self._payload`, call
   `self.add_provenance_*` and `self.add_lineage(...)` as you go
4. Re-export the class in `aqp/data/products/__init__.py`
5. Add a corresponding `DataMCPTool` in
   [aqp/data/mcp/tools/entities.py](../aqp/data/mcp/tools/entities.py)
6. Optional: add a REST route in
   [aqp/api/routes/data_entities.py](../aqp/api/routes/data_entities.py)

Don't forget tests under `tests/data/products/`.
