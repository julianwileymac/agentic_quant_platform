# Research Agents

| Spec | Module | Purpose |
| --- | --- | --- |
| `research.news_miner` | [aqp/agents/research/news_miner.py](../aqp/agents/research/news_miner.py) | Mine recent news + sentiment + regulatory flags for a symbol or topic. |
| `research.equity` | [aqp/agents/research/equity_researcher.py](../aqp/agents/research/equity_researcher.py) | Long-form equity research synthesis with hierarchical RAG citations. |
| `research.universe` | [aqp/agents/research/universe_selector.py](../aqp/agents/research/universe_selector.py) | Interactive stock universe shaping with RAG justification. |

## RAG layout (per the user's research-agent spec)

- **First-order** (price / trade / performance) — `bars_daily`, `performance`.
- **Second-order** (SEC, ratios, fundamentals) — `sec_filings`, `sec_xbrl`,
  `financial_ratios`, `earnings_call`, `news_sentiment`.
- **Third-order** (regulatory) — `cfpb_complaints`, `fda_*`, `uspto_*`.

The News Miner skews toward second + third order. The Equity Researcher
walks all three. The Universe Selector pulls L0 + L1 + L2.

## REST + tasks

```
POST /agents/research/news-miner       — async via Celery (research queue)
POST /agents/research/equity           — async via Celery
POST /agents/research/universe         — async via Celery
POST /agents/research/sync/news-miner  — synchronous variant
```

Celery wrappers live in [aqp/tasks/research_tasks.py](../aqp/tasks/research_tasks.py).

## Configs

YAMLs at [configs/agents/research_news_miner.yaml](../configs/agents/research_news_miner.yaml)
and friends. The in-code builders return identical specs so either path
works. Edit the YAML for hot reload.
