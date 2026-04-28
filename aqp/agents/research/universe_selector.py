"""Research agent: Universe Selector (interactive stock universe shaping)."""
from __future__ import annotations

from aqp.agents.spec import AgentSpec, GuardrailSpec, MemorySpec, ModelRef, RAGRef, ToolRef


SYSTEM = """You are a quant universe-curation agent. Given a thesis and constraints
(sector, market cap, liquidity, regulatory exposure), propose a candidate universe.

Required JSON output:
{
  "universe": ["AAPL.NASDAQ", ...],
  "buckets": {"core": [...], "watch": [...], "exclude": [...]},
  "filters_applied": [...],
  "rag_evidence": [{"vt_symbol": "...", "doc_id": "...", "corpus": "...", "snippet": "..."}],
  "rationale": "..."
}

Process:
1. Pull the platform's current managed universe via describe_bars.
2. Use hierarchy_browse with order=first to find symbols with adequate
   liquidity / coverage; use second to enrich with fundamentals.
3. Use regulatory_lookup to flag tail-risk candidates.
4. Persist the picks via the annotation tool with label="universe_picks".
"""


def build_universe_selector_spec() -> AgentSpec:
    return AgentSpec(
        name="research.universe",
        role="universe_selector",
        description="Interactive stock universe shaping with RAG justification.",
        system_prompt=SYSTEM,
        model=ModelRef(provider="ollama", model="", tier="deep", temperature=0.25),
        tools=[
            ToolRef(name="describe_bars"),
            ToolRef(name="hierarchy_browse"),
            ToolRef(name="rag_query"),
            ToolRef(name="regulatory_lookup"),
            ToolRef(name="annotation"),
        ],
        memory=MemorySpec(kind="redis_hybrid", role="research.universe", working_max=32),
        rag=[
            RAGRef(
                levels=["l0", "l1", "l2"],
                orders=["first", "second"],
                per_level_k=5,
                final_k=12,
            ),
        ],
        guardrails=GuardrailSpec(
            require_rationale=True,
            cost_budget_usd=0.75,
            rate_limit_per_minute=20,
        ),
        max_cost_usd=0.75,
        max_calls=15,
        annotations=["research", "universe"],
    )
