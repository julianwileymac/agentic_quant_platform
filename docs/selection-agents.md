# Selection Agents

The Selection team picks the top-N tickers for a
`(model, strategy, universe, agent)` quadruple. It is the bridge
between the Research team's universe candidates and the Trader team's
signal-emitter loop.

## Spec

`selection.stock_selector` — implemented in
[aqp/agents/selection/stock_selector.py](../aqp/agents/selection/stock_selector.py).

## RAG

| Layer | Used for |
| --- | --- |
| L0 (`decisions`) | Past `agent_decisions` outcomes — paper RAG#0. |
| L1 (`performance`) | Recent backtest performance windows. |
| L2 (`financial_ratios`, `sec_xbrl`) | Discriminate between similar candidates. |
| Tool: `regulatory_lookup` | Tail-risk veto. |

## Memory + annotations

Every pick is persisted via `annotation` with `label="pick"` and a
payload `{score, rationale, evidence, vetoed_by?}` so the optimisation
analysis layer can inspect the historical edge of each combo.

## REST

```
POST /agents/selection/run             — async via Celery
POST /agents/selection/sync            — synchronous variant
GET  /agents/selection/runs            — recent runs
GET  /agents/selection/annotations     — pick rationale history
```

## YAML

[configs/agents/selection_stock_selector.yaml](../configs/agents/selection_stock_selector.yaml).
