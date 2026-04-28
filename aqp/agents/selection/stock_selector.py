"""Selection agent: picks top-N tickers for a (model, strategy, universe, agent) combo."""
from __future__ import annotations

from aqp.agents.spec import AgentSpec, GuardrailSpec, MemorySpec, ModelRef, RAGRef, ToolRef


SYSTEM = """You are a quant selection agent. Inputs:
- candidate_universe: list[str]  (vt_symbols)
- model: str                     (ML model id we'd train on the picks)
- strategy: str                  (strategy id we'd run on the picks)
- target_horizon: str            (e.g. "5d", "20d", "60d")
- preferences: dict (optional)   (sector tilt, liquidity floor, ...)

Goal: pick the top N tickers (default N=10) that this combo is most
likely to perform well on. Use:

- L0 RAG (decisions corpus) to learn from past combos.
- L1 performance corpus to inspect recent performance windows.
- L2 fundamentals to discriminate between similar candidates.
- L3 regulatory_lookup as a tail-risk veto.
- annotation tool to persist each pick with its rationale.

Output JSON: {"picks": [{"vt_symbol": "...", "score": 0..1, "rationale": "...",
"evidence": [...]}], "vetoed": [...], "rationale": "...",
"model": "...", "strategy": "...", "horizon": "..."}
"""


def build_stock_selector_spec() -> AgentSpec:
    return AgentSpec(
        name="selection.stock_selector",
        role="stock_selector",
        description="Selects top-N tickers for a (model, strategy, universe, agent) combo.",
        system_prompt=SYSTEM,
        model=ModelRef(provider="ollama", model="", tier="deep", temperature=0.2),
        tools=[
            ToolRef(name="hierarchy_browse"),
            ToolRef(name="rag_query"),
            ToolRef(name="performance_window"),
            ToolRef(name="fundamentals_snapshot"),
            ToolRef(name="regulatory_lookup"),
            ToolRef(name="annotation"),
        ],
        memory=MemorySpec(kind="redis_hybrid", role="selection.stock_selector", working_max=64),
        rag=[
            RAGRef(
                levels=["l0", "l1"],
                orders=["first"],
                corpora=["decisions", "performance"],
                per_level_k=5,
                final_k=10,
            ),
            RAGRef(
                levels=["l2"],
                orders=["second"],
                corpora=["financial_ratios", "sec_xbrl"],
                per_level_k=4,
                final_k=8,
            ),
        ],
        guardrails=GuardrailSpec(
            require_rationale=True,
            cost_budget_usd=1.0,
            rate_limit_per_minute=20,
        ),
        max_cost_usd=1.0,
        max_calls=20,
        annotations=["selection", "alpha_base"],
    )
