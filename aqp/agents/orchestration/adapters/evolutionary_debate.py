"""``EvolutionaryDebateAdapter`` — RD-Agent-inspired four-role loop.

Runs Proposer -> Developer -> Critic -> Evaluator for at most
``ctx.extras['max_rounds']`` iterations. Every role is a registered
:class:`aqp.agents.spec.AgentSpec` driven through
:class:`aqp.agents.runtime.AgentRuntime` so:

- LLM calls go through ``router_complete`` (rule 2);
- data reads go through DataMCP tools the AgentSpec declares (rule 22);
- guardrails / cost caps are enforced by the underlying AgentRuntime
  (rule 12).

The adapter never imports ORM models, never calls ``router_complete``
directly, and never executes generated Python — the only path that
turns an LLM-emitted formula into something runnable is the existing
:mod:`aqp.data.expressions_dsl` AST sandbox.

Spec contract::

    adapter: EvolutionaryDebateAdapter
    adapter_kind: debate
    params:
      proposer_agent: assistant.evolutionary_proposer
      developer_agent: assistant.evolutionary_developer
      critic_agent: assistant.evolutionary_critic
      evaluator_agent: assistant.evolutionary_evaluator
      formula_field: formula
      rationale_field: rationale
      require_risk_constraints: true
    max_rounds: 3

Halt + bounds:

- Polls ``context.is_halted()`` between every role and between every
  round so a flipped kill switch interrupts mid-debate (rule 6).
- ``max_rounds`` is forwarded onto the ``AdapterContext.extras`` dict
  by ``WorkflowRuntime`` (Phase 1 fix — defect 2). The adapter still
  caps with ``settings.assistant_max_rounds`` as defence-in-depth.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from aqp.agents.orchestration.base import OrchestrationAdapter
from aqp.agents.orchestration.types import (
    AdapterContext,
    AdapterFailure,
    AdapterResult,
)
from aqp.assistants.critic_checks import CriticVerdict, run_deterministic_critic
from aqp.config import settings

logger = logging.getLogger(__name__)


class EvolutionaryDebateAdapter(OrchestrationAdapter):
    """Bounded Proposer / Developer / Critic / Evaluator loop."""

    adapter_kind = "debate"
    adapter_alias = "EvolutionaryDebateAdapter"
    adapter_source = "rd_agent"
    adapter_category = "evolutionary"
    adapter_tags = ("evolutionary", "bounded", "deterministic_critic")

    # ------------------------------------------------------------------
    def invoke(self, state: Any, context: AdapterContext) -> AdapterResult:
        start = time.perf_counter()
        params = dict(context.extras.get("params") or {})
        max_rounds_default = int(
            getattr(settings, "assistant_max_rounds", 0)
            or getattr(settings, "orchestration_max_debate_rounds", 2)
            or 2
        )
        spec_max_rounds = int(
            context.extras.get("max_rounds")
            or params.get("max_rounds")
            or max_rounds_default
        )
        max_rounds = max(1, min(spec_max_rounds, max_rounds_default))

        roles = self._resolve_roles(params)
        if isinstance(roles, str):
            return self._error(state, roles, start)

        formula_field = str(params.get("formula_field") or "formula")
        rationale_field = str(params.get("rationale_field") or "rationale")
        require_risk = bool(params.get("require_risk_constraints", True))

        merged: dict[str, Any] = dict(state) if isinstance(state, dict) else dict(state)  # noqa: SIM108
        merged.setdefault("evolutionary_history", [])
        breadcrumbs: list[dict[str, Any]] = []
        cost_total = 0.0
        n_calls_total = 0
        n_tool_calls_total = 0
        n_rag_hits_total = 0
        accepted_proposal: dict[str, Any] | None = None

        for round_idx in range(1, max_rounds + 1):
            if context.is_halted():
                return self._halted(merged, breadcrumbs, start, "halt before round")

            round_record: dict[str, Any] = {"round": round_idx}

            # 1) Proposer
            proposer_result = self._run_role(
                role="proposer",
                agent_spec_name=roles["proposer"],
                inputs=self._proposer_inputs(merged, params, round_idx),
                context=context,
                round_idx=round_idx,
                breadcrumbs=breadcrumbs,
            )
            cost_total += proposer_result["cost_usd"]
            n_calls_total += proposer_result["n_calls"]
            n_tool_calls_total += proposer_result["n_tool_calls"]
            n_rag_hits_total += proposer_result["n_rag_hits"]
            proposal = proposer_result["output"]
            round_record["proposal"] = proposal
            if context.is_halted():
                return self._halted(merged, breadcrumbs, start, "halt after proposer")

            # 2) Developer
            developer_result = self._run_role(
                role="developer",
                agent_spec_name=roles["developer"],
                inputs=self._developer_inputs(proposal, params, round_idx),
                context=context,
                round_idx=round_idx,
                breadcrumbs=breadcrumbs,
            )
            cost_total += developer_result["cost_usd"]
            n_calls_total += developer_result["n_calls"]
            n_tool_calls_total += developer_result["n_tool_calls"]
            n_rag_hits_total += developer_result["n_rag_hits"]
            developed = developer_result["output"] or proposal
            round_record["developed"] = developed
            if context.is_halted():
                return self._halted(merged, breadcrumbs, start, "halt after developer")

            # 3) Deterministic critic checks (Python-only, no LLM).
            verdict = run_deterministic_critic(
                developed,
                formula_field=formula_field,
                rationale_field=rationale_field,
                require_risk_constraints=require_risk,
            )
            self._record_breadcrumb(
                breadcrumbs,
                role="deterministic_critic",
                round_idx=round_idx,
                status="ok" if verdict.passed else "rejected",
                start=start,
                attributes={"violations": verdict.violations},
            )
            round_record["deterministic_critic"] = verdict.to_dict()

            # 4) LLM critic — receives the deterministic verdict so it can
            #    explain failures back to the proposer in plain English.
            critic_result = self._run_role(
                role="critic",
                agent_spec_name=roles["critic"],
                inputs=self._critic_inputs(developed, verdict, params, round_idx),
                context=context,
                round_idx=round_idx,
                breadcrumbs=breadcrumbs,
            )
            cost_total += critic_result["cost_usd"]
            n_calls_total += critic_result["n_calls"]
            n_tool_calls_total += critic_result["n_tool_calls"]
            n_rag_hits_total += critic_result["n_rag_hits"]
            critique = critic_result["output"]
            round_record["critique"] = critique
            if context.is_halted():
                return self._halted(merged, breadcrumbs, start, "halt after critic")

            # Hard reject when the deterministic checks fail; the LLM
            # critic verdict is informative only at that point.
            if not verdict.passed:
                round_record["status"] = "rejected"
                merged.setdefault("evolutionary_history", []).append(round_record)
                continue

            # 5) Evaluator — accepts or asks for another round.
            evaluator_result = self._run_role(
                role="evaluator",
                agent_spec_name=roles["evaluator"],
                inputs=self._evaluator_inputs(
                    developed, critique, verdict, params, round_idx
                ),
                context=context,
                round_idx=round_idx,
                breadcrumbs=breadcrumbs,
            )
            cost_total += evaluator_result["cost_usd"]
            n_calls_total += evaluator_result["n_calls"]
            n_tool_calls_total += evaluator_result["n_tool_calls"]
            n_rag_hits_total += evaluator_result["n_rag_hits"]
            evaluation = evaluator_result["output"]
            round_record["evaluation"] = evaluation

            decision = self._coerce_decision(evaluation)
            round_record["decision"] = decision
            merged.setdefault("evolutionary_history", []).append(round_record)
            if decision == "accept":
                accepted_proposal = developed
                merged["evolutionary_accepted"] = developed
                merged["evolutionary_evaluation"] = evaluation
                break

        if accepted_proposal is None:
            merged["evolutionary_accepted"] = None
            merged["evolutionary_terminal_reason"] = "max_rounds_exhausted"

        existing = list(merged.get("adapter_breadcrumbs") or [])
        merged["adapter_breadcrumbs"] = existing + breadcrumbs
        return AdapterResult(
            state=merged,
            status=AdapterResult.STATUS_COMPLETED,
            breadcrumbs=breadcrumbs,
            cost_usd=cost_total,
            n_calls=n_calls_total,
            n_tool_calls=n_tool_calls_total,
            n_rag_hits=n_rag_hits_total,
            duration_ms=(time.perf_counter() - start) * 1000.0,
        )

    # ------------------------------------------------------------------
    # Roles
    # ------------------------------------------------------------------

    def _resolve_roles(self, params: dict[str, Any]) -> dict[str, str] | str:
        required = ("proposer_agent", "developer_agent", "critic_agent", "evaluator_agent")
        missing = [r for r in required if not params.get(r)]
        if missing:
            return f"EvolutionaryDebateAdapter missing role(s): {missing}"
        return {
            "proposer": str(params["proposer_agent"]),
            "developer": str(params["developer_agent"]),
            "critic": str(params["critic_agent"]),
            "evaluator": str(params["evaluator_agent"]),
        }

    def _run_role(
        self,
        *,
        role: str,
        agent_spec_name: str,
        inputs: dict[str, Any],
        context: AdapterContext,
        round_idx: int,
        breadcrumbs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        from aqp.agents.registry import get_agent_spec
        from aqp.agents.runtime import AgentRuntime

        start = time.perf_counter()
        try:
            agent_spec = get_agent_spec(agent_spec_name)
        except Exception as exc:  # noqa: BLE001
            self._record_breadcrumb(
                breadcrumbs,
                role=role,
                round_idx=round_idx,
                status="error",
                start=start,
                attributes={"error": f"unknown agent spec {agent_spec_name!r}: {exc}"},
            )
            return {
                "output": {},
                "cost_usd": 0.0,
                "n_calls": 0,
                "n_tool_calls": 0,
                "n_rag_hits": 0,
                "status": "error",
            }

        try:
            runtime = AgentRuntime(
                spec=agent_spec,
                run_id=str(uuid.uuid4()),
                task_id=context.request_id,
                context=getattr(context, "extras", {}).get("request_context"),
            )
            result = runtime.run(inputs=inputs)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "EvolutionaryDebateAdapter role %s/%s crashed", role, agent_spec_name
            )
            self._record_breadcrumb(
                breadcrumbs,
                role=role,
                round_idx=round_idx,
                status="error",
                start=start,
                attributes={"error": str(exc)},
            )
            return {
                "output": {},
                "cost_usd": 0.0,
                "n_calls": 0,
                "n_tool_calls": 0,
                "n_rag_hits": 0,
                "status": "error",
            }

        status = getattr(result, "status", "completed")
        output = getattr(result, "output", {}) or {}
        self._record_breadcrumb(
            breadcrumbs,
            role=role,
            round_idx=round_idx,
            status=status,
            start=start,
            attributes={
                "agent_spec": agent_spec_name,
                "agent_run_id": getattr(result, "run_id", None),
                "n_tool_calls": int(getattr(result, "n_tool_calls", 0) or 0),
                "n_rag_hits": int(getattr(result, "n_rag_hits", 0) or 0),
            },
            cost_usd=float(getattr(result, "cost_usd", 0.0) or 0.0),
        )
        return {
            "output": dict(output) if isinstance(output, dict) else {},
            "cost_usd": float(getattr(result, "cost_usd", 0.0) or 0.0),
            "n_calls": int(getattr(result, "n_calls", 0) or 0),
            "n_tool_calls": int(getattr(result, "n_tool_calls", 0) or 0),
            "n_rag_hits": int(getattr(result, "n_rag_hits", 0) or 0),
            "status": status,
        }

    # ------------------------------------------------------------------
    # Per-role input projections
    # ------------------------------------------------------------------

    def _proposer_inputs(
        self,
        merged: dict[str, Any],
        params: dict[str, Any],
        round_idx: int,
    ) -> dict[str, Any]:
        prompt = (
            f"Round {round_idx} — propose a new candidate. "
            f"Goal: {params.get('goal') or 'maximise risk-adjusted return'}."
        )
        return {
            "prompt": prompt,
            "round": round_idx,
            "history": list(merged.get("evolutionary_history") or [])[-3:],
            "constraints": dict(params.get("constraints") or {}),
            "user_intent": merged.get("inputs", {}).get("prompt", ""),
        }

    def _developer_inputs(
        self,
        proposal: dict[str, Any],
        params: dict[str, Any],
        round_idx: int,
    ) -> dict[str, Any]:
        return {
            "prompt": (
                f"Round {round_idx} — refine the candidate proposal into a "
                "vectorised implementation. Do NOT execute code."
            ),
            "proposal": dict(proposal),
            "constraints": dict(params.get("constraints") or {}),
            "round": round_idx,
        }

    def _critic_inputs(
        self,
        developed: dict[str, Any],
        verdict: CriticVerdict,
        params: dict[str, Any],
        round_idx: int,
    ) -> dict[str, Any]:
        return {
            "prompt": (
                f"Round {round_idx} — critique the developed candidate. The "
                "deterministic critic has already run; explain the violations "
                "(if any) and whether the candidate is otherwise sound."
            ),
            "developed": dict(developed),
            "deterministic_verdict": verdict.to_dict(),
            "round": round_idx,
            "constraints": dict(params.get("constraints") or {}),
        }

    def _evaluator_inputs(
        self,
        developed: dict[str, Any],
        critique: dict[str, Any],
        verdict: CriticVerdict,
        params: dict[str, Any],
        round_idx: int,
    ) -> dict[str, Any]:
        return {
            "prompt": (
                f"Round {round_idx} — score the candidate and decide accept "
                "or revise. Output JSON with keys: decision in "
                "[accept, revise, reject], score, rationale."
            ),
            "developed": dict(developed),
            "critique": dict(critique),
            "deterministic_verdict": verdict.to_dict(),
            "round": round_idx,
        }

    @staticmethod
    def _coerce_decision(evaluation: Any) -> str:
        if isinstance(evaluation, dict):
            raw = str(evaluation.get("decision") or "").strip().lower()
            if raw in ("accept", "approved", "ship"):
                return "accept"
            if raw in ("reject", "rejected", "stop"):
                return "reject"
        return "revise"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _record_breadcrumb(
        self,
        breadcrumbs: list[dict[str, Any]],
        *,
        role: str,
        round_idx: int,
        status: str,
        start: float,
        attributes: dict[str, Any] | None = None,
        cost_usd: float | None = None,
    ) -> None:
        crumb: dict[str, Any] = {
            "adapter": self.adapter_alias,
            "node": role,
            "round": round_idx,
            "status": status,
            "duration_ms": round((time.perf_counter() - start) * 1000.0, 3),
        }
        if attributes:
            crumb["attributes"] = attributes
        if cost_usd is not None:
            crumb["cost_usd"] = float(cost_usd)
        breadcrumbs.append(crumb)

    def _halted(
        self,
        merged: dict[str, Any],
        breadcrumbs: list[dict[str, Any]],
        start: float,
        reason: str,
    ) -> AdapterResult:
        breadcrumbs.append(
            {
                "adapter": self.adapter_alias,
                "node": "halt_check",
                "status": "halted",
                "duration_ms": round((time.perf_counter() - start) * 1000.0, 3),
                "reason": reason,
            }
        )
        merged["halt_token"] = True
        return AdapterResult(
            state=merged,
            status=AdapterResult.STATUS_HALTED,
            failure=AdapterFailure(message=reason, kind="halted"),
            breadcrumbs=breadcrumbs,
            duration_ms=(time.perf_counter() - start) * 1000.0,
        )

    def _error(self, state: Any, message: str, start: float) -> AdapterResult:
        return AdapterResult(
            state=state if isinstance(state, dict) else dict(state),
            status=AdapterResult.STATUS_ERROR,
            failure=AdapterFailure(message=message, kind="error"),
            duration_ms=(time.perf_counter() - start) * 1000.0,
        )


__all__ = ["EvolutionaryDebateAdapter"]
