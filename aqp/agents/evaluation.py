"""Agent evaluation harness — golden-trace replay + judge prompts + metric writers.

Two evaluation modes:

- **Golden replay** — feed a list of ``(case_id, inputs, expected)`` cases
  through :class:`AgentRuntime` and record per-case metrics.
- **LLM judge** — for each case, ask a quick-tier LLM to score the
  produced output against the expected one on a 0..10 scale (TradingAgents
  reflection pattern).

Both modes write to ``agent_evaluations`` + ``agent_eval_metrics`` so
the webui can render an eval dashboard.
"""
from __future__ import annotations

import json
import logging
import statistics
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from aqp.agents.runtime import AgentRunResult, AgentRuntime
from aqp.agents.spec import AgentSpec

logger = logging.getLogger(__name__)


@dataclass
class EvalCase:
    """One evaluation case."""

    case_id: str
    inputs: dict[str, Any]
    expected: dict[str, Any] | None = None
    tags: list[str] = field(default_factory=list)


@dataclass
class CaseResult:
    case_id: str
    output: dict[str, Any]
    cost_usd: float
    metrics: dict[str, Any] = field(default_factory=dict)
    passed: bool | None = None
    error: str | None = None


@dataclass
class EvalReport:
    spec_name: str
    eval_set: str
    cases: list[CaseResult] = field(default_factory=list)
    aggregate: dict[str, Any] = field(default_factory=dict)
    evaluation_id: str | None = None


_JUDGE_SYSTEM = (
    "You are an evaluation judge. Score the candidate against the expected "
    "answer on a 0..10 scale. Respond strictly as JSON: "
    '{"score": <0..10>, "rationale": "..."}'
)


def evaluate(
    spec: AgentSpec,
    cases: Iterable[EvalCase],
    *,
    eval_set_name: str = "adhoc",
    use_llm_judge: bool = False,
) -> EvalReport:
    """Run ``cases`` against ``spec`` and persist the result."""
    case_list = list(cases)
    report = EvalReport(spec_name=spec.name, eval_set=eval_set_name)
    eval_id = _open_eval_row(spec=spec, eval_set_name=eval_set_name, n_cases=len(case_list))
    report.evaluation_id = eval_id
    for case in case_list:
        try:
            runtime = AgentRuntime(spec)
            result: AgentRunResult = runtime.run(case.inputs)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Eval case %s failed to run", case.case_id)
            cr = CaseResult(case_id=case.case_id, output={}, cost_usd=0.0, error=str(exc))
            report.cases.append(cr)
            _persist_metric(eval_id, case.case_id, "error", text_value=str(exc), passed=False)
            continue
        metrics = _baseline_metrics(case, result)
        passed = bool(metrics.get("structural_pass", True))
        if use_llm_judge and case.expected:
            jm = _llm_judge(spec, case, result.output)
            metrics.update(jm)
            score = float(jm.get("judge_score", 0.0) or 0.0)
            passed = passed and score >= 6.0
        cr = CaseResult(
            case_id=case.case_id,
            output=result.output,
            cost_usd=result.cost_usd,
            metrics=metrics,
            passed=passed,
        )
        report.cases.append(cr)
        for metric, value in metrics.items():
            _persist_metric(
                eval_id,
                case.case_id,
                metric,
                value=float(value) if isinstance(value, (int, float)) else None,
                text_value=str(value) if not isinstance(value, (int, float, bool)) else None,
                passed=passed if metric in {"structural_pass", "judge_score"} else None,
            )
    report.aggregate = _aggregate(report.cases)
    _close_eval_row(eval_id, report)
    return report


def _baseline_metrics(case: EvalCase, result: AgentRunResult) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "cost_usd": result.cost_usd,
        "n_calls": result.n_calls,
        "n_tool_calls": result.n_tool_calls,
        "n_rag_hits": result.n_rag_hits,
        "structural_pass": isinstance(result.output, dict) and bool(result.output),
    }
    if case.expected:
        try:
            expected_keys = set(case.expected.keys())
            actual_keys = set(result.output.keys()) if isinstance(result.output, dict) else set()
            metrics["key_overlap"] = len(expected_keys & actual_keys) / max(1, len(expected_keys))
        except Exception:  # noqa: BLE001
            metrics["key_overlap"] = 0.0
    return metrics


def _aggregate(cases: list[CaseResult]) -> dict[str, Any]:
    if not cases:
        return {}
    n = len(cases)
    n_passed = sum(1 for c in cases if c.passed)
    cost = [c.cost_usd for c in cases]
    return {
        "n_cases": n,
        "n_passed": n_passed,
        "pass_rate": round(n_passed / n, 4),
        "total_cost_usd": round(sum(cost), 4),
        "mean_cost_usd": round(statistics.fmean(cost) if cost else 0.0, 6),
    }


def _llm_judge(
    spec: AgentSpec, case: EvalCase, candidate_output: dict[str, Any]
) -> dict[str, Any]:
    try:
        from aqp.config import settings
        from aqp.llm.providers.router import router_complete

        provider = spec.model.provider or settings.llm_provider
        model = settings.llm_quick_model or spec.model.model
        prompt = (
            f"Expected:\n{json.dumps(case.expected, default=str, indent=2)}\n\n"
            f"Candidate:\n{json.dumps(candidate_output, default=str, indent=2)}"
        )
        res = router_complete(
            provider=provider,
            model=model,
            messages=[
                {"role": "system", "content": _JUDGE_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            tier="quick",
        )
        try:
            parsed = json.loads((res.content or "").strip().strip("`"))
        except Exception:
            parsed = {"score": 0.0, "rationale": res.content or ""}
        return {
            "judge_score": float(parsed.get("score", 0.0) or 0.0),
            "judge_rationale": str(parsed.get("rationale", "")),
        }
    except Exception:  # noqa: BLE001
        logger.debug("LLM judge unavailable", exc_info=True)
        return {}


# ---------------------------------------------------------------------- DB
def _open_eval_row(*, spec: AgentSpec, eval_set_name: str, n_cases: int) -> str | None:
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_agents import AgentEvaluation

        eid = str(uuid.uuid4())
        with SessionLocal() as session:
            session.add(
                AgentEvaluation(
                    id=eid,
                    spec_name=spec.name,
                    eval_set_name=eval_set_name,
                    n_cases=n_cases,
                    started_at=datetime.utcnow(),
                )
            )
            session.commit()
        return eid
    except Exception:  # pragma: no cover
        logger.debug("Cannot open eval row", exc_info=True)
        return None


def _close_eval_row(eval_id: str | None, report: EvalReport) -> None:
    if eval_id is None:
        return
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_agents import AgentEvaluation

        with SessionLocal() as session:
            row = session.query(AgentEvaluation).filter(AgentEvaluation.id == eval_id).one_or_none()
            if row is not None:
                row.aggregate = report.aggregate
                row.n_passed = sum(1 for c in report.cases if c.passed)
                row.completed_at = datetime.utcnow()
                session.commit()
    except Exception:  # pragma: no cover
        logger.debug("Cannot close eval row", exc_info=True)


def _persist_metric(
    eval_id: str | None,
    case_id: str,
    metric: str,
    *,
    value: float | None = None,
    text_value: str | None = None,
    passed: bool | None = None,
) -> None:
    if eval_id is None:
        return
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_agents import AgentEvalMetric

        with SessionLocal() as session:
            session.add(
                AgentEvalMetric(
                    evaluation_id=eval_id,
                    case_id=case_id,
                    metric=metric,
                    value=value,
                    text_value=text_value,
                    passed=passed,
                )
            )
            session.commit()
    except Exception:  # pragma: no cover
        logger.debug("Cannot persist metric", exc_info=True)


__all__ = [
    "CaseResult",
    "EvalCase",
    "EvalReport",
    "evaluate",
]
