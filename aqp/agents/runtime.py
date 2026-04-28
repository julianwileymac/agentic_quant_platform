"""AgentRuntime — execute an :class:`AgentSpec` end-to-end with telemetry.

The runtime turns a declarative spec into a real agent run:

1. Snapshot + persist the spec version (hash-locked → ``agent_spec_versions``).
2. Resolve tools from :data:`aqp.agents.tools.TOOL_REGISTRY`.
3. Build a :class:`HierarchicalRAG` plan from the spec's ``rag`` clauses
   and stitch retrieved context into the system + user messages.
4. Wire :class:`RedisHybridMemory` for working / episodic / reflection
   recall (TradingAgents' ``past_context`` pattern).
5. Call ``router_complete`` with deep/quick tier per
   :attr:`AgentSpec.model.tier`.
6. Validate output + apply guardrails.
7. Persist a complete trace: one ``agent_runs_v2`` row + N
   ``agent_run_steps`` rows + optional ``agent_run_artifacts``.

The runtime is deliberately lean — heavy multi-agent orchestration
lives in :mod:`aqp.agents.graph` (LangGraph). Use this for a single
spec; use the graph builder when chaining specs.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from aqp.agents.spec import AgentSpec, RAGRef
from aqp.config import settings
from aqp.llm.providers.router import router_complete

logger = logging.getLogger(__name__)


@dataclass
class StepRecord:
    seq: int
    kind: str
    name: str
    inputs: dict[str, Any] = field(default_factory=dict)
    output: dict[str, Any] = field(default_factory=dict)
    cost_usd: float = 0.0
    duration_ms: float = 0.0
    error: str | None = None


@dataclass
class AgentRunResult:
    run_id: str
    spec_name: str
    status: str
    output: dict[str, Any]
    cost_usd: float
    n_calls: int
    n_tool_calls: int
    n_rag_hits: int
    steps: list[StepRecord] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "spec_name": self.spec_name,
            "status": self.status,
            "output": self.output,
            "cost_usd": self.cost_usd,
            "n_calls": self.n_calls,
            "n_tool_calls": self.n_tool_calls,
            "n_rag_hits": self.n_rag_hits,
            "steps": [s.__dict__ for s in self.steps],
            "error": self.error,
        }


class GuardrailViolation(RuntimeError):
    """Raised when a guardrail check fails."""


class AgentRuntime:
    """Executor for a single :class:`AgentSpec`.

    Reuses (a thin wrapper over) the existing
    :class:`aqp.agents.capability_runtime.CapabilityRuntime` patterns
    for tool resolution + guardrail validation + cost tracking, then
    layers in the new RAG + Redis memory bindings.
    """

    def __init__(
        self,
        spec: AgentSpec,
        *,
        run_id: str | None = None,
        task_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        self.spec = spec
        self.run_id = run_id or str(uuid.uuid4())
        self.task_id = task_id
        self.session_id = session_id
        self._steps: list[StepRecord] = []
        self._cost = 0.0
        self._calls = 0
        self._tool_calls = 0
        self._rag_hits = 0
        self._tool_cache: dict[str, Any] = {}

    # ------------------------------------------------------------------ public API
    def run(self, inputs: Mapping[str, Any]) -> AgentRunResult:
        """Execute the spec end-to-end. Always returns a result.

        Errors do not raise; they're captured into ``status="error"`` so
        the caller can persist a partial trace and surface it in the UI.
        """
        spec_version_id = self._snapshot_spec()
        self._open_run(inputs=dict(inputs), spec_version_id=spec_version_id)
        try:
            user_prompt = self._render_user_prompt(inputs)
            rag_context = self._gather_rag_context(user_prompt)
            episode_context = self._gather_episodic_context(user_prompt)
            messages = self._build_messages(
                user_prompt=user_prompt,
                rag_context=rag_context,
                episode_context=episode_context,
            )
            llm_result = self._invoke_llm(messages)
            output = self._parse_output(llm_result)
            self._guardrail_check(output, llm_result)
            self._record_episode(user_prompt, output)
            result = self._finalise(status="completed", output=output)
        except GuardrailViolation as exc:
            logger.warning("Guardrail violation in %s: %s", self.spec.name, exc)
            result = self._finalise(status="rejected", output={}, error=str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.exception("AgentRuntime failed for %s", self.spec.name)
            result = self._finalise(status="error", output={}, error=str(exc))
        return result

    # ------------------------------------------------------------------ DB plumbing
    def _snapshot_spec(self) -> str | None:
        from aqp.agents.registry import persist_spec

        return persist_spec(self.spec)

    def _open_run(self, *, inputs: dict[str, Any], spec_version_id: str | None) -> None:
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_agents import AgentRunV2

            with SessionLocal() as session:
                session.add(
                    AgentRunV2(
                        id=self.run_id,
                        spec_name=self.spec.name,
                        spec_version_id=spec_version_id,
                        task_id=self.task_id,
                        session_id=self.session_id,
                        status="running",
                        inputs=inputs,
                        started_at=datetime.utcnow(),
                    )
                )
                session.commit()
        except Exception:  # noqa: BLE001
            logger.debug("Could not open agent_runs_v2 row", exc_info=True)

    def _persist_step(self, step: StepRecord) -> None:
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_agents import AgentRunStep

            with SessionLocal() as session:
                session.add(
                    AgentRunStep(
                        run_id=self.run_id,
                        seq=step.seq,
                        kind=step.kind,
                        name=step.name,
                        inputs=_safe_json(step.inputs),
                        output=_safe_json(step.output),
                        cost_usd=step.cost_usd,
                        duration_ms=step.duration_ms,
                        error=step.error,
                    )
                )
                session.commit()
        except Exception:  # noqa: BLE001
            logger.debug("Could not persist agent_run_step", exc_info=True)

    def _finalise(self, *, status: str, output: dict[str, Any], error: str | None = None) -> AgentRunResult:
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_agents import AgentRunV2

            with SessionLocal() as session:
                row = session.query(AgentRunV2).filter(AgentRunV2.id == self.run_id).one_or_none()
                if row is not None:
                    row.status = status
                    row.output = _safe_json(output)
                    row.error = error
                    row.cost_usd = self._cost
                    row.n_calls = self._calls
                    row.n_tool_calls = self._tool_calls
                    row.n_rag_hits = self._rag_hits
                    row.completed_at = datetime.utcnow()
                    session.commit()
        except Exception:  # noqa: BLE001
            logger.debug("Could not finalise agent_runs_v2 row", exc_info=True)
        return AgentRunResult(
            run_id=self.run_id,
            spec_name=self.spec.name,
            status=status,
            output=output,
            cost_usd=self._cost,
            n_calls=self._calls,
            n_tool_calls=self._tool_calls,
            n_rag_hits=self._rag_hits,
            steps=list(self._steps),
            error=error,
        )

    # ------------------------------------------------------------------ steps
    def _next_seq(self) -> int:
        return len(self._steps) + 1

    def _add_step(self, **kwargs: Any) -> StepRecord:
        step = StepRecord(seq=self._next_seq(), **kwargs)
        self._steps.append(step)
        self._persist_step(step)
        return step

    # ------------------------------------------------------------------ RAG
    def _gather_rag_context(self, query: str) -> str:
        if not self.spec.rag:
            return ""
        try:
            from aqp.rag import HierarchicalRAG, RAGPlan, get_default_rag
        except Exception:  # pragma: no cover
            logger.debug("RAG unavailable; skipping retrieval", exc_info=True)
            return ""
        rag: HierarchicalRAG = get_default_rag()
        sections: list[str] = []
        total_hits = 0
        for clause in self.spec.rag:
            sections.extend(self._rag_clause(rag, clause, query))
            total_hits += clause.final_k
        self._rag_hits = total_hits
        return "\n\n".join(s for s in sections if s)

    def _rag_clause(self, rag: Any, clause: RAGRef, query: str) -> list[str]:
        from aqp.rag.hierarchy import RAGPlan

        out: list[str] = []
        start = time.perf_counter()
        if clause.corpora:
            collected: list[Any] = []
            for corpus in clause.corpora:
                for level in clause.levels:
                    hits = rag.query(
                        query,
                        level=level,
                        corpus=corpus,
                        k=clause.per_level_k,
                        rerank=clause.rerank,
                        compress=clause.compress,
                    )
                    collected.extend(hits)
            collected.sort(key=lambda h: getattr(h, "score", 0.0), reverse=True)
            top = collected[: clause.final_k]
        else:
            plan = RAGPlan(
                query=query,
                levels=tuple(clause.levels),
                orders=tuple(clause.orders),
                per_level_k=clause.per_level_k,
                final_k=clause.final_k,
                rerank=clause.rerank,
                compress=clause.compress,
            )
            top = rag.walk(plan)
        elapsed = (time.perf_counter() - start) * 1000.0
        self._add_step(
            kind="rag",
            name=f"rag_clause:{','.join(clause.levels)}",
            inputs={"query": query, "clause": clause.model_dump()},
            output={
                "n_hits": len(top),
                "top_doc_ids": [getattr(h, "doc_id", "") for h in top[:5]],
            },
            duration_ms=elapsed,
        )
        if not top:
            return out
        if clause.inject_as == "memory":
            for h in top:
                self._working_push(getattr(h, "text", ""))
            return out
        rendered = "\n".join(
            f"[{getattr(h, 'corpus', '?')}/{getattr(h, 'level', '?')}] {getattr(h, 'text', '')[:600]}"
            for h in top
        )
        out.append(f"## RAG context ({clause.inject_as})\n{rendered}")
        return out

    # ------------------------------------------------------------------ memory
    def _memory(self):
        if self.spec.memory.disabled():
            return None
        cached = self._tool_cache.get("__memory__")
        if cached is not None:
            return cached
        try:
            if self.spec.memory.kind == "redis_hybrid":
                from aqp.llm.memory import RedisHybridMemory

                mem = RedisHybridMemory(
                    self.spec.memory_role(),
                    working_max=self.spec.memory.working_max,
                )
            elif self.spec.memory.kind == "hybrid":
                from aqp.llm.memory import HybridMemory

                mem = HybridMemory(self.spec.memory_role())
            elif self.spec.memory.kind == "bm25":
                from aqp.llm.memory import BM25Memory

                mem = BM25Memory(self.spec.memory_role())
            else:
                mem = None
        except Exception:  # noqa: BLE001
            logger.debug("Memory binding failed", exc_info=True)
            mem = None
        self._tool_cache["__memory__"] = mem
        return mem

    def _working_push(self, message: str) -> None:
        mem = self._memory()
        if mem is None or not hasattr(mem, "working_push"):
            return
        mem.working_push(self.run_id, message)

    def _gather_episodic_context(self, query: str) -> str:
        mem = self._memory()
        if mem is None:
            return ""
        try:
            if hasattr(mem, "recall_reflections"):
                hits = mem.recall_reflections(query, k=self.spec.memory.retrieval_top_k)
            elif hasattr(mem, "recall"):
                hits = mem.recall(query, k=self.spec.memory.retrieval_top_k)
            else:
                hits = []
        except Exception:  # noqa: BLE001
            logger.debug("Episodic recall failed", exc_info=True)
            return ""
        if not hits:
            return ""
        if hits and isinstance(hits[0], str):
            text = "\n".join(f"- {h}" for h in hits)
        else:
            text = "\n".join(f"- {getattr(h, 'lesson', str(h))}" for h in hits)
        self._add_step(
            kind="memory",
            name="recall_reflections",
            inputs={"query": query},
            output={"n_hits": len(hits)},
        )
        return f"## Past reflections\n{text}"

    def _record_episode(self, situation: str, output: dict[str, Any]) -> None:
        mem = self._memory()
        if mem is None or not getattr(self.spec.memory, "write_through", True):
            return
        if not hasattr(mem, "remember_episode"):
            return
        lesson = json.dumps({"output_keys": list(output.keys())[:10]}, default=str)
        try:
            mem.remember_episode(situation=situation[:2000], lesson=lesson, outcome=None, metadata={"run_id": self.run_id})
        except Exception:  # noqa: BLE001
            logger.debug("remember_episode failed", exc_info=True)

    # ------------------------------------------------------------------ messages + LLM
    def _render_user_prompt(self, inputs: Mapping[str, Any]) -> str:
        # Prefer an explicit ``prompt`` input; fall back to a JSON dump
        # of the inputs when not provided.
        if isinstance(inputs.get("prompt"), str) and inputs["prompt"].strip():
            return str(inputs["prompt"])
        return json.dumps({k: v for k, v in inputs.items()}, default=str, indent=2)

    def _build_messages(
        self,
        *,
        user_prompt: str,
        rag_context: str,
        episode_context: str,
    ) -> list[dict[str, str]]:
        system_parts: list[str] = []
        if self.spec.system_prompt:
            system_parts.append(self.spec.system_prompt)
        if rag_context:
            system_parts.append(rag_context)
        if episode_context:
            system_parts.append(episode_context)
        return [
            {"role": "system", "content": "\n\n".join(system_parts).strip() or "You are a helpful agent."},
            {"role": "user", "content": user_prompt},
        ]

    def _invoke_llm(self, messages: list[dict[str, str]]) -> Any:
        start = time.perf_counter()
        provider = self.spec.model.provider or settings.llm_provider
        model = self.spec.model.model or (
            settings.llm_quick_model if self.spec.model.tier == "quick" else settings.llm_deep_model
        )
        try:
            res = router_complete(
                provider=provider,
                model=model,
                messages=messages,
                temperature=self.spec.model.temperature,
                max_tokens=self.spec.model.max_tokens,
                tier=self.spec.model.tier,
                **self.spec.model.extras,
            )
        except Exception as exc:  # noqa: BLE001
            self._add_step(
                kind="llm",
                name=f"{provider}:{model}",
                inputs={"messages": messages[-2:]},
                output={},
                duration_ms=(time.perf_counter() - start) * 1000.0,
                error=str(exc),
            )
            raise
        self._calls += 1
        self._cost += float(getattr(res, "cost_usd", 0.0) or 0.0)
        self._add_step(
            kind="llm",
            name=f"{provider}:{model}",
            inputs={"messages": messages[-2:]},
            output={
                "content": (getattr(res, "content", "") or "")[:8000],
                "tokens": int(getattr(res, "total_tokens", 0) or 0),
            },
            cost_usd=float(getattr(res, "cost_usd", 0.0) or 0.0),
            duration_ms=(time.perf_counter() - start) * 1000.0,
        )
        return res

    def _parse_output(self, llm_result: Any) -> dict[str, Any]:
        text = (getattr(llm_result, "content", "") or "").strip()
        if not text:
            return {"text": ""}
        # Try to extract JSON; otherwise wrap raw text.
        try:
            return _try_json(text)
        except Exception:
            return {"text": text}

    # ------------------------------------------------------------------ guardrails
    def _guardrail_check(self, output: dict[str, Any], llm_result: Any) -> None:
        guards = self.spec.guardrails
        if guards.cost_budget_usd > 0 and self._cost > guards.cost_budget_usd:
            raise GuardrailViolation(
                f"Cost {self._cost:.4f} USD exceeded budget {guards.cost_budget_usd:.4f} USD"
            )
        if self._calls > self.spec.max_calls:
            raise GuardrailViolation(
                f"Call count {self._calls} exceeded spec.max_calls={self.spec.max_calls}"
            )
        if guards.forbidden_terms:
            text = json.dumps(output, default=str).lower()
            hits = [t for t in guards.forbidden_terms if t in text]
            if hits:
                raise GuardrailViolation(f"Forbidden terms: {hits}")
        if guards.require_rationale and isinstance(output, dict) and not _has_rationale(output):
            raise GuardrailViolation("Output missing rationale field")
        if guards.min_confidence is not None and isinstance(output, dict):
            conf = output.get("confidence")
            if isinstance(conf, (int, float)) and float(conf) < float(guards.min_confidence):
                raise GuardrailViolation(
                    f"Confidence {conf} < min {guards.min_confidence}"
                )


def _try_json(text: str) -> dict[str, Any]:
    text = text.strip()
    # Strip ```json ... ``` fences if present
    if text.startswith("```"):
        nl = text.find("\n")
        if nl >= 0:
            text = text[nl + 1 :]
        if text.endswith("```"):
            text = text[: -3]
        text = text.strip()
    return json.loads(text)


def _has_rationale(output: dict[str, Any]) -> bool:
    keys = {k.lower() for k in output.keys()}
    return bool({"rationale", "reason", "reasoning", "explanation", "thesis"} & keys)


def _safe_json(value: Any) -> Any:
    try:
        json.dumps(value, default=str)
        return value
    except Exception:
        return {"_unserialisable": str(value)[:1000]}


def runtime_for(spec_name: str, **kwargs: Any) -> AgentRuntime:
    """Convenience: look up a spec by name and build a runtime."""
    from aqp.agents.registry import get_agent_spec

    return AgentRuntime(get_agent_spec(spec_name), **kwargs)


__all__ = [
    "AgentRunResult",
    "AgentRuntime",
    "GuardrailViolation",
    "StepRecord",
    "runtime_for",
]
