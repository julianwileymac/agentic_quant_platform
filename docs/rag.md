# Hierarchical RAG (Alpha-GPT Style)

The platform's retrieval-augmented generation layer is a faithful port
of the four-level hierarchical RAG described in *Alpha-GPT: Human-AI
Interactive Alpha Mining* (`inspiration/2308.00016v2.pdf`, Section 3.2,
Figure 3) on top of **Redis Stack / RediSearch** instead of the paper's
Faiss store. All vectors, tag indexes, working-memory queues, and
reflection logs share one Redis instance configured by
`AQP_REDIS_URL`.

## Levels (paper RAG#0..#3)

| Level | Paper id | Purpose | Default corpora |
| --- | --- | --- | --- |
| `l0` | RAG#0 | Past agent decisions / equity reports / backtest outcomes — the "alpha base" the LLM consults to characterise prior wins/losses. | `decisions`, `performance` |
| `l1` | RAG#1 | High-level domain (`price_volume`, `fundamental`, `news_sentiment`, `regulatory`, ...). | One per registered L1 in [aqp/rag/orders.py](../aqp/rag/orders.py). |
| `l2` | RAG#2 | Sub-domain (`disclosures`, `earnings_call`, `cfpb_complaint`, `fda_recall`, `patent_grant`, ...). | One per registered L2. |
| `l3` | RAG#3 | Specific data fields, document chunks, complaint narratives. | All leaf chunk corpora. |

## Knowledge orders

Orthogonal to the levels, every corpus belongs to one of three knowledge
orders (the user's research-agent specification):

- **first** — bars / trades / performance.
- **second** — SEC filings, fundamentals, ratios, earnings calls, news.
- **third** — CFPB complaints, FDA applications + adverse events +
  recalls, USPTO patents + trademarks + assignments.

The full corpus catalog lives in
[aqp/rag/orders.py::OrderCatalog](../aqp/rag/orders.py).

## Architecture

```
+-------------------+         +---------------------+
| AgentRuntime      |  query  | HierarchicalRAG     |
|  (Phase 3)        |-------->|  - walk(plan)       |
+-------------------+         |  - query(level=...) |
                              |  - recall_for_prompt|
                              +----------+----------+
                                         |
                +--------+----------+----+----+----------+
                |        |          |         |         |
                v        v          v         v         v
         Embedder    Chunker     Reranker  Compressor  Raptor
         (BGE-M3)   (token /    (BGE-      (cosine    (UMAP +
                    section /    reranker)  filter)    GMM)
                    semantic)
                                |
                                v
                       +-----------------+
                       | RedisVectorStore|
                       |  RediSearch HNSW|
                       |  + tag filters  |
                       +-----------------+
                                |
                                v
                          Redis Stack
                       (vectors + tags +
                        working memory +
                        reflection log)
```

## Public API

```python
from aqp.rag import HierarchicalRAG, RAGPlan, get_default_rag

rag = get_default_rag()

# Direct retrieval at one level.
hits = rag.query(
    "How are banks handling overdraft complaints?",
    level="l3",
    corpus="cfpb_complaints",
    k=8,
)

# Top-down navigation (paper Section 3.2 autonomous mode).
hits = rag.walk(
    RAGPlan(
        query="Find tail risk for AAPL from regulatory signals",
        levels=("l1", "l2", "l3"),
        orders=("second", "third"),
        vt_symbol="AAPL.NASDAQ",
        per_level_k=5,
        final_k=8,
    )
)

# Convenience: ready-to-splice prompt context block.
context_md = rag.recall_for_prompt(
    "Latest FDA recalls affecting medical-device makers in our universe"
)
```

## Indexers

Each corpus has one indexer under [aqp/rag/indexers/](../aqp/rag/indexers/);
all indexers are registered in `INDEXER_REGISTRY` so the Celery task
`aqp.tasks.rag_tasks.index_corpus` can dispatch by name. Indexers are
defensive — if their source ORM table or Iceberg namespace isn't
available yet, they log and return zero so a partial install doesn't
crash bootstrap.

## RAPTOR hierarchical summarisation

`aqp.rag.raptor.build_tree` ports the FinGPT RAPTOR pattern (UMAP +
Gaussian Mixture clustering, LLM-summary at each level). Summary nodes
are written back into the same RAG store at L1/L2 via
`HierarchicalRAG.index_summary`, so the agent can drill from a
high-level synopsis down to the supporting leaf chunks.

## Observability

Every retrieval is optionally logged to the `rag_queries` table
(controlled by `AQP_RAG_AUDIT_ENABLED`). The webui's `/rag/explorer`
page renders these as a heat-map of hot corpora over time.

## Don'ts

- **Don't** query Redis directly — go through `HierarchicalRAG`.
- **Don't** write embeddings outside `aqp.rag.indexers.*`. Adding a new
  source means writing an indexer + registering its corpus in
  [aqp/rag/orders.py](../aqp/rag/orders.py).
- **Don't** replace the existing `ChromaStore`. Chroma stays for the
  legacy dataset / code metadata indexes; Redis is the new
  hierarchical RAG.
