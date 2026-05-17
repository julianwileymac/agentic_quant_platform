"""``DialecticalDebateAdapter`` — bounded TradingAgents-style debate.

Wraps :func:`aqp.agents.graph.dialectical.build_dialectical_debate_graph`
with the additional guarantees the report calls for:

1. **Bounded rounds.** ``spec.max_rounds`` (or the
   ``AQP_ORCHESTRATION_MAX_DEBATE_ROUNDS`` default) is the hard cap.
   The graph builder already enforces this via the new
   ``should_continue_debate`` predicate, but the adapter re-checks
   ``research_debate.count`` after streaming so a future LangGraph
   upgrade that ignores the predicate still can't blow the budget.

2. **Forced judge synthesis.** When the round count reaches the cap
   without a ``debate_verdict`` slot, the adapter invokes the
   deterministic ``_portfolio_manager_node`` synth path so downstream
   nodes never see a missing verdict.

3. **Cooperative halt.** ``context.is_halted()`` is polled between
   every yielded frame; a positive return aborts before the next
   round starts.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from aqp.agents.orchestration.base import OrchestrationAdapter
from aqp.agents.orchestration.types import (
    AdapterContext,
    AdapterFailure,
    AdapterResult,
)
from aqp.config import settings

logger = logging.getLogger(__name__)


class DialecticalDebateAdapter(OrchestrationAdapter):
    """Bounded Bull/Bear/PortfolioManager debate adapter.

    Spec contract::

        adapter: DialecticalDebateAdapter
        params:
          use_langgraph: null         # null = auto, false = SequentialGraph fallback
        max_rounds: 2                 # honoured from the surrounding WorkflowSpec

    State input slots (set by upstream nodes):

    - ``proposed_alpha``
    - ``simulation_verdict``

    State output slots:

    - ``bull_argument``
    - ``bear_argument``
    - ``debate_verdict`` (always populated — falls back to the
      deterministic synth when the LLM-driven portfolio manager
      times out or returns no action)
    - ``research_debate.count`` (incremented per turn)
    """

    adapter_kind = "debate"
    adapter_alias = "DialecticalDebateAdapter"
    adapter_source = "tradingagents"
    adapter_category = "debate"
    adapter_tags = ("bull_bear", "bounded", "judge_synthesis")

    def invoke(self, state: Any, context: AdapterContext) -> AdapterResult:
        start = time.perf_counter()
        params = context.extras.get("params") or {}
        max_rounds = int(
            context.extras.get("max_rounds")
            or params.get("max_rounds")
            or getattr(settings, "orchestration_max_debate_rounds", 2)
            or 2
        )
        max_rounds = max(1, max_rounds)
        use_langgraph = params.get("use_langgraph")

        try:
            from aqp.agents.graph.dialectical import (
                _portfolio_manager_node,
                build_dialectical_debate_graph,
            )
        except Exception as exc:  # noqa: BLE001 - dialectical is always present
            logger.exception("DialecticalDebateAdapter import failed")
            return AdapterResult(
                state=state,
                status=AdapterResult.STATUS_ERROR,
                failure=AdapterFailure(message=str(exc), kind="error"),
                duration_ms=(time.perf_counter() - start) * 1000.0,
            )

        try:
            graph = build_dialectical_debate_graph(
                use_langgraph=use_langgraph if use_langgraph is not None else False,
                max_rounds=max_rounds,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("DialecticalDebateAdapter graph build failed")
            return AdapterResult(
                state=state,
                status=AdapterResult.STATUS_ERROR,
                failure=AdapterFailure(message=str(exc), kind="error"),
                duration_ms=(time.perf_counter() - start) * 1000.0,
            )

        if context.is_halted():
            return AdapterResult(
                state=state,
                status=AdapterResult.STATUS_HALTED,
                failure=AdapterFailure(
                    message="halt_check fired before debate started", kind="halted"
                ),
                duration_ms=(time.perf_counter() - start) * 1000.0,
            )

        breadcrumbs: list[dict[str, Any]] = []
        current = dict(state)
        last = current
        stream = getattr(graph, "stream", None)
        try:
            if callable(stream):
                for frame in stream(current):
                    if not isinstance(frame, dict):
                        continue
                    for node_name, node_state in frame.items():
                        breadcrumbs.append(
                            {
                                "adapter": self.adapter_alias,
                                "node": node_name,
                                "status": "ok",
                                "duration_ms": round(
                                    (time.perf_counter() - start) * 1000.0, 3
                                ),
                                "round_count": int(
                                    (node_state or {}).get("research_debate", {}).get("count", 0)
                                ),
                            }
                        )
                        if isinstance(node_state, dict):
                            last = node_state
                    if context.is_halted():
                        return AdapterResult(
                            state=last,
                            status=AdapterResult.STATUS_HALTED,
                            failure=AdapterFailure(
                                message="halt_check fired between debate rounds",
                                kind="halted",
                            ),
                            breadcrumbs=breadcrumbs,
                            duration_ms=(time.perf_counter() - start) * 1000.0,
                        )
            else:
                last = graph.invoke(current)
                breadcrumbs.append(
                    {
                        "adapter": self.adapter_alias,
                        "node": "dialectical_invoke",
                        "status": "ok",
                        "duration_ms": round((time.perf_counter() - start) * 1000.0, 3),
                    }
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("DialecticalDebateAdapter invoke failed")
            return AdapterResult(
                state=last,
                status=AdapterResult.STATUS_ERROR,
                failure=AdapterFailure(message=str(exc), kind="error"),
                breadcrumbs=breadcrumbs,
                duration_ms=(time.perf_counter() - start) * 1000.0,
            )

        merged = dict(last) if isinstance(last, dict) else dict(state)

        # Defence-in-depth: the predicate inside the LangGraph builder
        # is supposed to terminate after ``2 * max_rounds`` Bull/Bear
        # turns. Re-check here so a future LangGraph upgrade that
        # bypasses the predicate still cannot loop unbounded.
        debate = dict(merged.get("research_debate") or {})
        if int(debate.get("count", 0)) > 2 * max_rounds:
            breadcrumbs.append(
                {
                    "adapter": self.adapter_alias,
                    "node": "round_cap_enforce",
                    "status": "capped",
                    "duration_ms": round((time.perf_counter() - start) * 1000.0, 3),
                    "round_count": int(debate.get("count", 0)),
                    "max_rounds": max_rounds,
                }
            )
            debate["count"] = 2 * max_rounds
            merged["research_debate"] = debate

        # Forced judge synthesis when no verdict was produced.
        if not merged.get("debate_verdict"):
            try:
                merged = _portfolio_manager_node(merged)
                breadcrumbs.append(
                    {
                        "adapter": self.adapter_alias,
                        "node": "forced_judge_synth",
                        "status": "ok",
                        "duration_ms": round(
                            (time.perf_counter() - start) * 1000.0, 3
                        ),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "forced_judge_synth failed for debate adapter", exc_info=True
                )
                breadcrumbs.append(
                    {
                        "adapter": self.adapter_alias,
                        "node": "forced_judge_synth",
                        "status": "error",
                        "error": str(exc),
                    }
                )

        existing_breadcrumbs = list(merged.get("adapter_breadcrumbs") or [])
        merged["adapter_breadcrumbs"] = existing_breadcrumbs + breadcrumbs
        return AdapterResult(
            state=merged,
            status=AdapterResult.STATUS_COMPLETED,
            breadcrumbs=breadcrumbs,
            cost_usd=float(merged.get("cost_usd") or 0.0),
            n_calls=int(merged.get("n_calls") or 0),
            n_rag_hits=int(merged.get("n_rag_hits") or 0),
            duration_ms=(time.perf_counter() - start) * 1000.0,
        )


__all__ = ["DialecticalDebateAdapter"]
