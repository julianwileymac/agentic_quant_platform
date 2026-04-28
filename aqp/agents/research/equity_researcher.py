"""Research agent: Equity Researcher (FinRobot-style with hierarchical RAG)."""
from __future__ import annotations

from aqp.agents.spec import AgentSpec, GuardrailSpec, MemorySpec, ModelRef, RAGRef, ToolRef


SYSTEM = """You are a senior equity research analyst. Produce a comprehensive equity research note.

Mandatory sections (JSON keys): tagline, company_overview, investment_overview,
valuation_overview, risks, competitor_analysis, news_summary, regulatory_summary,
catalysts, major_takeaways, rationale.

Process:
1. Use fundamentals_snapshot for the latest financial state.
2. Use hierarchy_browse to walk L1->L2->L3 across SEC filings, ratios,
   earnings calls, news, and regulatory corpora (CFPB / FDA / USPTO).
3. Use rag_query to drill into specific corpora when needed.
4. Use regulatory_lookup to enumerate filings against the issuer.
Constraint: Cite the corpus + score for every claim that came from RAG.
"""


def build_equity_researcher_spec() -> AgentSpec:
    return AgentSpec(
        name="research.equity",
        role="equity_researcher",
        description="Long-form equity research synthesis with hierarchical RAG.",
        system_prompt=SYSTEM,
        model=ModelRef(provider="ollama", model="", tier="deep", temperature=0.2),
        tools=[
            ToolRef(name="fundamentals_snapshot"),
            ToolRef(name="news_digest"),
            ToolRef(name="hierarchy_browse"),
            ToolRef(name="rag_query"),
            ToolRef(name="regulatory_lookup"),
            ToolRef(name="annotation"),
        ],
        memory=MemorySpec(kind="redis_hybrid", role="research.equity", working_max=64),
        rag=[
            RAGRef(
                levels=["l1", "l2"],
                orders=["second"],
                corpora=["sec_filings", "sec_xbrl", "financial_ratios", "earnings_call"],
                per_level_k=5,
                final_k=12,
            ),
            RAGRef(
                levels=["l3"],
                orders=["third"],
                corpora=["cfpb_complaints", "fda_recalls", "uspto_patents"],
                per_level_k=3,
                final_k=8,
            ),
        ],
        guardrails=GuardrailSpec(
            require_rationale=True,
            cost_budget_usd=1.5,
            rate_limit_per_minute=20,
            forbidden_terms=["guaranteed return"],
        ),
        max_cost_usd=1.5,
        max_calls=20,
        annotations=["research", "equity"],
    )
