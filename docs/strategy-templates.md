# Strategy template catalog (Phase 7 of the multi-tenant rollout)

Read-only strategy templates — QuantConnect LEAN's
``Algorithm.Python/*.py`` examples first, with hooks for
community + internal libraries — are ingested into the polymorphic
[`resources`](../aqp/persistence/models_resources.py) table and
surfaced to users + agents via the strategy template browser, the
MCP catalog, and the AST translator.

## Hard rule

Hard rule 35 in [`AGENTS.md`](../AGENTS.md): "Read-only strategy
templates (LEAN, community, internal references) MUST be loaded as
``resources`` rows with ``resource_type='strategy_template'``. The
AST translator lives in ``aqp/strategies/lean/translator.py``; new
translators register through the same pattern."

## Ingestion

```bash
# One-shot: clone LEAN + ingest every Algorithm.Python/*.py
python -m scripts.ingest_lean_templates --clone

# Re-ingest from a local checkout
LEAN_REPO_PATH=/opt/Lean python -m scripts.ingest_lean_templates

# Dry-run (parse + report only)
python -m scripts.ingest_lean_templates --lean-path /opt/Lean --dry-run
```

The ingester is idempotent — re-running with a newer LEAN revision
overwrites the matching rows in place. Each Resource carries the
parsed metadata (`class_name`, `base_class`, `asset_classes`,
`indicators`, `universe_symbols`, `tags`) plus the raw LEAN source
in `meta.raw_source` so the translator + frontend preview don't
need to re-read the file system.

## Translator

```python
from aqp.strategies.lean.translator import translate_lean_to_framework

skeleton = translate_lean_to_framework(lean_source)
```

The translator rewrites the LEAN AST into an
[`aqp.strategies.framework.FrameworkAlgorithm`](../aqp/strategies/framework.py)
skeleton. The mapping covers:

| LEAN                                  | AQP target                                 |
| ------------------------------------- | ------------------------------------------ |
| `Initialize`                          | `prepare`                                  |
| `OnData`                              | `on_bar`                                   |
| `OnSecuritiesChanged`                 | `on_universe_changed`                      |
| `self.AddEquity("SPY")`               | `ctx.add_equity("SPY")`                    |
| `self.AddOption("SPY")`               | `ctx.add_option("SPY")`                    |
| `self.AddCrypto("BTCUSD")`            | `ctx.add_crypto("BTCUSD")`                 |
| `self.SetCash(100000)`                | captured as cfg `starting_cash`            |
| `self.SetStartDate / SetEndDate`      | captured as cfg `start_date` / `end_date`  |
| `self.MACD(...)` / `self.SMA(...)`    | `aqp.data.indicators.MACD(...)`            |
| `self.MarketOrder(symbol, qty)`       | `ctx.market_order(symbol, qty)`            |
| `self.SetHoldings(symbol, fraction)`  | `ctx.set_holdings(symbol, fraction)`       |

Anything unmapped becomes a `# TODO(lean-translate)` comment so the
user can finish the port — translation is never silent.

## Agent surface

| Tool                                            | Purpose |
| ----------------------------------------------- | ------- |
| `data.strategies.templates.search`              | Filter by tag / asset class / framework |
| `data.strategies.templates.describe`            | Full Resource payload including raw source |
| `data.strategies.templates.clone_to_workspace`  | Fork into the calling user's workspace, optionally with the translator applied |

Cloning emits a `resource_relations.relation='translated_from'`
edge back to the source, so the ownership graph can audit
provenance — `data.ownership.tree` over the cloned Resource
returns the lineage chain back to the original LEAN class.

## REST surface

| Method + path                          | Purpose |
| -------------------------------------- | ------- |
| `GET /strategies/templates`            | List + filter |
| `GET /strategies/templates/{id}`       | Describe + raw source |
| `POST /strategies/templates/clone`     | Clone (mirrors the MCP tool) |

## Frontend

The browser lives at `/strategy-development/templates`. The grouped
list groups by primary asset class; the preview pane renders the
LEAN source in a monospace block with a "Clone to my workspace"
button (with a checkbox to toggle translation).

Free-text inputs that reference a specific strategy template are
forbidden — use `<EntityPicker kind="strategy_templates" />`.

## Cross-reference

- [`docs/ownership-graph.md`](ownership-graph.md) — the
  `translated_from` / `clones` edges live in the graph projection.
- [`docs/data-mcp.md`](data-mcp.md) — the
  `data.strategies.templates.*` tools are MCP-registered like every
  other agent surface.
- [`docs/metadata-cache.md`](metadata-cache.md) — the
  `strategy_templates` Redis cache category powers the EntityPicker.
