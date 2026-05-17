"""``LangGraphAdapter`` — wraps the five canonical graph builders.

Routes to one of the existing builders in
:mod:`aqp.agents.graph.builder` (and the dialectical one in
:mod:`aqp.agents.graph.dialectical`) by ``WorkflowSpec.params["builder"]``.
The wrapped graph keeps its existing LangGraph-optional / SequentialGraph
fallback semantics; the adapter never imports LangGraph itself.

Halt semantics
--------------
The adapter calls ``graph.stream(...)`` (or, on LangGraph builds that
don't expose ``stream``, ``graph.invoke(...)``) and polls
``context.is_halted()`` between yielded frames. Streaming gives
per-node halt granularity for free.

Per-node breadcrumbs are written into the state under
``adapter_breadcrumbs`` so the Phase 5 studio can render the exact
node order downstream.
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

logger = logging.getLogger(__name__)


_BUILDER_REGISTRY = {
    "research": "build_research_graph",
    "trader": "build_trader_graph",
    "full_pipeline": "build_full_pipeline_graph",
    "research_debate": "build_research_debate_graph",
    "quant_research_pipeline": "build_quant_research_pipeline_graph",
    "dialectical": "build_dialectical_debate_graph",
}


class LangGraphAdapter(OrchestrationAdapter):
    """Wraps existing AQP graph builders behind the adapter contract.

    Spec contract::

        adapter: LangGraphAdapter
        params:
          builder: dialectical            # one of _BUILDER_REGISTRY
          use_langgraph: null             # null = auto, false = force fallback
          builder_kwargs: {max_rounds: 2} # forwarded into the builder factory
    """

    adapter_kind = "graph"
    adapter_alias = "LangGraphAdapter"
    adapter_source = "aqp"
    adapter_category = "graph"
    adapter_tags = ("langgraph", "sequential_fallback")

    def invoke(self, state: Any, context: AdapterContext) -> AdapterResult:
        start = time.perf_counter()
        params = context.extras.get("params") or {}
        builder_alias = str(params.get("builder") or state.get("builder_alias") or "research")
        use_langgraph = params.get("use_langgraph")
        builder_kwargs = dict(params.get("builder_kwargs") or {})

        try:
            graph = self._build_graph(builder_alias, use_langgraph, builder_kwargs)
        except KeyError as exc:
            return AdapterResult(
                state=state,
                status=AdapterResult.STATUS_ERROR,
                failure=AdapterFailure(message=str(exc), kind="error"),
                duration_ms=(time.perf_counter() - start) * 1000.0,
            )

        breadcrumbs: list[dict[str, Any]] = []
        current = dict(state)
        last = current
        try:
            stream = getattr(graph, "stream", None)
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
                            }
                        )
                        if isinstance(node_state, dict):
                            last = node_state
                    if context.is_halted():
                        return AdapterResult(
                            state=last,
                            status=AdapterResult.STATUS_HALTED,
                            breadcrumbs=breadcrumbs
                            + [
                                {
                                    "adapter": self.adapter_alias,
                                    "node": "halt_check",
                                    "status": "halted",
                                    "duration_ms": round(
                                        (time.perf_counter() - start) * 1000.0, 3
                                    ),
                                }
                            ],
                            failure=AdapterFailure(
                                message="halt_check fired between stream frames",
                                kind="halted",
                            ),
                            duration_ms=(time.perf_counter() - start) * 1000.0,
                        )
            else:
                last = graph.invoke(current)
                breadcrumbs.append(
                    {
                        "adapter": self.adapter_alias,
                        "node": builder_alias,
                        "status": "ok",
                        "duration_ms": round(
                            (time.perf_counter() - start) * 1000.0, 3
                        ),
                    }
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("LangGraphAdapter invoke failed for %s", builder_alias)
            return AdapterResult(
                state=last,
                status=AdapterResult.STATUS_ERROR,
                failure=AdapterFailure(message=str(exc), kind="error"),
                breadcrumbs=breadcrumbs,
                duration_ms=(time.perf_counter() - start) * 1000.0,
            )

        merged = dict(last) if isinstance(last, dict) else {"output": last}
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

    # ------------------------------------------------------------------ helpers
    def _build_graph(
        self,
        builder_alias: str,
        use_langgraph: Any,
        builder_kwargs: dict[str, Any],
    ) -> Any:
        if builder_alias not in _BUILDER_REGISTRY:
            raise KeyError(
                f"unknown builder alias {builder_alias!r}; "
                f"expected one of {sorted(_BUILDER_REGISTRY)}"
            )
        symbol = _BUILDER_REGISTRY[builder_alias]
        if builder_alias == "dialectical":
            from aqp.agents.graph.dialectical import build_dialectical_debate_graph

            builder_fn = build_dialectical_debate_graph
        else:
            from aqp.agents.graph import builder as builder_mod

            builder_fn = getattr(builder_mod, symbol)
        kwargs: dict[str, Any] = dict(builder_kwargs)
        if use_langgraph is not None:
            kwargs["use_langgraph"] = bool(use_langgraph)
        return builder_fn(**kwargs)


__all__ = ["LangGraphAdapter"]
