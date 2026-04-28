"""Research agent: News Miner.

Mines recent news for a symbol or topic, scores sentiment, and pulls
contextualised snippets via the L2 ``news_sentiment`` corpus + L3
regulatory corpora (CFPB / FDA recalls). Mirrors the FinGPT
"causal weekly news window" pattern.
"""
from __future__ import annotations

from aqp.agents.spec import AgentSpec, GuardrailSpec, MemorySpec, ModelRef, RAGRef, ToolRef


SYSTEM = """You are a financial news mining analyst. Given a symbol or topic, you:
1. Pull recent news + sentiment (use the news_digest and sentiment_score tools).
2. Cross-check regulatory signals via regulatory_lookup and the third-order RAG.
3. Use rag_query / hierarchy_browse to fetch relevant context (L1=news_sentiment, L2=news_articles, L3=cfpb/fda).
4. Emit a JSON report with: top_stories, sentiment_distribution, regulatory_flags, trading_implications, rationale.
Constraint: Do NOT recommend specific trades. You produce findings only.
"""


def build_news_miner_spec() -> AgentSpec:
    return AgentSpec(
        name="research.news_miner",
        role="news_miner",
        description="Mines news + sentiment + regulatory flags for a symbol/topic.",
        system_prompt=SYSTEM,
        model=ModelRef(provider="ollama", model="", tier="quick", temperature=0.3),
        tools=[
            ToolRef(name="news_digest"),
            ToolRef(name="sentiment_score"),
            ToolRef(name="rag_query"),
            ToolRef(name="hierarchy_browse"),
            ToolRef(name="regulatory_lookup"),
            ToolRef(name="annotation"),
        ],
        memory=MemorySpec(kind="redis_hybrid", role="research.news_miner", working_max=32),
        rag=[
            RAGRef(
                levels=["l1", "l2"],
                orders=["second"],
                corpora=["news_sentiment"],
                per_level_k=8,
                final_k=10,
            ),
            RAGRef(
                levels=["l3"],
                orders=["third"],
                corpora=["cfpb_complaints", "fda_recalls", "fda_adverse_events"],
                per_level_k=4,
                final_k=8,
            ),
        ],
        guardrails=GuardrailSpec(
            require_rationale=True,
            forbidden_terms=["guaranteed return", "risk free"],
            cost_budget_usd=0.5,
            rate_limit_per_minute=30,
        ),
        max_cost_usd=0.5,
        max_calls=12,
        annotations=["research", "news"],
    )
