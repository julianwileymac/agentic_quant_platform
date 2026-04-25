"""LLM-as-judge over a backtest's agent-decision trace.

This is the post-hoc HITL critique surface (see plan milestone B). The
judge consumes the per-``(symbol, timestamp)`` decision rows the
TradingAgents-style crew already persists, plus the equity curve and
realised-vs-forward returns, and emits a structured
:class:`JudgeReport` containing per-decision findings the UI can render
inline and offer "apply suggestion" -> counterfactual replay.

Two registered judges live here:

- :class:`LLMJudge` — direct LLM call via the platform router.
- :class:`CrewJudge` — adapter over any registered :class:`BaseFinancialCrew`
  (e.g. ``MarketForecaster``) so users can use *any* agent crew as a
  judge without us hand-coding bespoke prompt logic.

Both share a :class:`BaseJudge` interface so the API + Celery layer can
treat them interchangeably and the registry surface (``kind=judge``)
populates the wizard dropdown.
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, Field, field_validator

from aqp.agents.financial.base import extract_json
from aqp.core.registry import register
from aqp.llm.ollama_client import complete

logger = logging.getLogger(__name__)


Severity = Literal["info", "warn", "error"]
Verdict = Literal["keep", "edit", "veto"]
Action = Literal["BUY", "SELL", "HOLD"]


class Finding(BaseModel):
    """One decision-level critique row."""

    decision_id: str | None = None
    vt_symbol: str = ""
    ts: str = ""
    severity: Severity = "info"
    verdict: Verdict = "keep"
    recommended_action: Action = "HOLD"
    recommended_size_pct: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""

    @field_validator("severity", mode="before")
    @classmethod
    def _norm_severity(cls, v: Any) -> str:
        s = str(v or "info").lower()
        return s if s in {"info", "warn", "error"} else "info"

    @field_validator("verdict", mode="before")
    @classmethod
    def _norm_verdict(cls, v: Any) -> str:
        s = str(v or "keep").lower()
        return s if s in {"keep", "edit", "veto"} else "keep"

    @field_validator("recommended_action", mode="before")
    @classmethod
    def _norm_action(cls, v: Any) -> str:
        s = str(v or "HOLD").upper()
        return s if s in {"BUY", "SELL", "HOLD"} else "HOLD"


class JudgeReport(BaseModel):
    """Top-level structured critique.

    Persisted as one row per backtest in ``agent_judge_reports`` and
    surfaced verbatim through the Backtest Detail "Judge" tab.
    """

    judge_class: str
    backtest_id: str | None = None
    score: float = 0.0
    summary: str = ""
    findings: list[Finding] = Field(default_factory=list)
    cost_usd: float = 0.0
    provider: str = ""
    model: str = ""
    rubric: str = "default"

    def to_json_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Base interface
# ---------------------------------------------------------------------------


class BaseJudge(ABC):
    """Common signature every registered judge satisfies."""

    name: str = "judge"

    @abstractmethod
    def evaluate(
        self,
        decisions: list[dict[str, Any]] | pd.DataFrame,
        equity_curve: pd.Series | None = None,
        *,
        backtest_id: str | None = None,
        bars: pd.DataFrame | None = None,
        rubric: str | None = None,
    ) -> JudgeReport:
        """Critique a decision trace and return a :class:`JudgeReport`."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_DEFAULT_RUBRIC = """\
Rate each decision against these axes (1=poor, 5=excellent):

  1. Evidence-action alignment — did the analyst summary support the chosen action?
  2. Sizing discipline — was size_pct proportional to confidence?
  3. Risk awareness — did the rationale acknowledge plausible downside?
  4. Cost-benefit — did the projected edge justify the LLM token cost?
  5. Forward fit — given the realised forward return, was the call profitable?

Then assign:
  severity ∈ {info, warn, error}        (escalate when sizing or action conflict with evidence)
  verdict  ∈ {keep, edit, veto}         (recommend an override when the call is materially wrong)
  recommended_action ∈ {BUY, SELL, HOLD}
  recommended_size_pct ∈ [0, 1]

Only flag verdict=veto for unambiguously wrong calls; default to keep when ambiguous.
"""


_SYSTEM_TEMPLATE = """\
You are an experienced trade-review analyst auditing the decisions of an
LLM trader crew. Be terse, evidence-driven, and skeptical.

{rubric}

Respond ONLY with JSON of shape:
{{
  "score": number in [0, 1] across all decisions,
  "summary": "one-paragraph overall verdict",
  "findings": [
    {{
      "decision_id": "<id>",
      "vt_symbol": "<sym>",
      "ts": "<iso ts>",
      "severity": "info" | "warn" | "error",
      "verdict": "keep" | "edit" | "veto",
      "recommended_action": "BUY" | "SELL" | "HOLD",
      "recommended_size_pct": number in [0, 1],
      "rationale": "<one sentence>"
    }}
  ]
}}
"""


def _decisions_to_records(
    decisions: list[dict[str, Any]] | pd.DataFrame,
) -> list[dict[str, Any]]:
    if isinstance(decisions, pd.DataFrame):
        rows = decisions.to_dict(orient="records")
    else:
        rows = list(decisions or [])
    out: list[dict[str, Any]] = []
    for row in rows:
        if hasattr(row, "model_dump"):
            row = row.model_dump(mode="json")
        rec = dict(row or {})
        ts = rec.get("ts") or rec.get("timestamp")
        if hasattr(ts, "isoformat"):
            ts = ts.isoformat()
        out.append(
            {
                "decision_id": str(rec.get("id", "") or ""),
                "vt_symbol": str(rec.get("vt_symbol", "") or ""),
                "ts": str(ts or ""),
                "action": str(rec.get("action", "HOLD") or "HOLD").upper(),
                "size_pct": float(rec.get("size_pct", 0.0) or 0.0),
                "confidence": float(rec.get("confidence", 0.5) or 0.5),
                "rating": str(rec.get("rating", "hold") or "hold"),
                "rationale": str(rec.get("rationale", "") or "")[:400],
                "token_cost_usd": float(rec.get("token_cost_usd", 0.0) or 0.0),
                "forward_return": rec.get("forward_return"),
            }
        )
    return out


def _equity_summary(equity: pd.Series | None) -> dict[str, Any]:
    if equity is None or equity.empty:
        return {}
    eq = equity.dropna()
    if eq.empty:
        return {}
    rets = eq.pct_change().dropna()
    cummax = eq.cummax()
    dd = (eq - cummax) / cummax
    return {
        "n_days": int(len(eq)),
        "total_return_pct": round(float(eq.iloc[-1] / eq.iloc[0] - 1) * 100, 2),
        "ann_vol_pct": round(float(rets.std() * (252**0.5)) * 100, 2) if len(rets) > 1 else None,
        "sharpe": (
            round(float(rets.mean() / rets.std() * (252**0.5)), 2)
            if len(rets) > 1 and rets.std() > 0
            else None
        ),
        "max_drawdown_pct": round(float(dd.min()) * 100, 2) if len(dd) else None,
    }


# ---------------------------------------------------------------------------
# Direct LLM judge
# ---------------------------------------------------------------------------


@register("LLMJudge", kind="judge", tags=("llm", "judge"))
class LLMJudge(BaseJudge):
    """Direct LLM-as-judge: one call over the full decision trace."""

    name = "llm_judge"

    def __init__(
        self,
        tier: str = "deep",
        provider: str | None = None,
        model: str | None = None,
        rubric: str = "default",
        cost_budget_usd: float = 1.0,
        max_decisions_per_call: int = 50,
    ) -> None:
        self.tier = tier
        self.provider = provider
        self.model = model
        self.rubric = rubric
        self.cost_budget_usd = float(cost_budget_usd)
        self.max_decisions_per_call = max(1, int(max_decisions_per_call))

    def evaluate(
        self,
        decisions: list[dict[str, Any]] | pd.DataFrame,
        equity_curve: pd.Series | None = None,
        *,
        backtest_id: str | None = None,
        bars: pd.DataFrame | None = None,
        rubric: str | None = None,
    ) -> JudgeReport:
        records = _decisions_to_records(decisions)
        if not records:
            return JudgeReport(
                judge_class=type(self).__name__,
                backtest_id=backtest_id,
                summary="No decisions to evaluate.",
                rubric=rubric or self.rubric,
            )

        rubric_text = _DEFAULT_RUBRIC if (rubric or self.rubric) == "default" else (rubric or self.rubric)
        system = _SYSTEM_TEMPLATE.format(rubric=rubric_text)
        equity = _equity_summary(equity_curve)

        chunks = [
            records[i : i + self.max_decisions_per_call]
            for i in range(0, len(records), self.max_decisions_per_call)
        ]

        all_findings: list[Finding] = []
        scores: list[float] = []
        summaries: list[str] = []
        total_cost = 0.0
        provider_used = ""
        model_used = ""

        for chunk in chunks:
            user = (
                f"backtest_id: {backtest_id or 'n/a'}\n"
                f"equity_summary: {json.dumps(equity, default=str)}\n"
                f"decisions:\n{json.dumps(chunk, default=str)[:14000]}\n"
            )
            try:
                result = complete(
                    tier=self.tier,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    provider=self.provider,
                    model=self.model,
                )
            except Exception:
                logger.exception("LLMJudge call failed")
                continue
            total_cost += float(getattr(result, "cost_usd", 0.0) or 0.0)
            provider_used = provider_used or getattr(result, "provider", "") or ""
            model_used = model_used or getattr(result, "model", "") or ""
            payload = extract_json(result.content)
            scores.append(float(payload.get("score", 0.0) or 0.0))
            summaries.append(str(payload.get("summary", "") or ""))
            for raw in payload.get("findings", []) or []:
                try:
                    all_findings.append(Finding(**raw))
                except Exception:
                    logger.warning("LLMJudge: skipping malformed finding %r", raw)
            if total_cost >= self.cost_budget_usd:
                logger.info(
                    "LLMJudge: stopping after %d/%d chunks — cost budget %s exhausted",
                    chunks.index(chunk) + 1,
                    len(chunks),
                    self.cost_budget_usd,
                )
                break

        score = float(sum(scores) / len(scores)) if scores else 0.0
        summary = " ".join(s for s in summaries if s)[:1500]

        return JudgeReport(
            judge_class=type(self).__name__,
            backtest_id=backtest_id,
            score=score,
            summary=summary,
            findings=all_findings,
            cost_usd=round(total_cost, 6),
            provider=provider_used,
            model=model_used,
            rubric=rubric or self.rubric,
        )


# ---------------------------------------------------------------------------
# Crew adapter judge
# ---------------------------------------------------------------------------


@register("CrewJudge", kind="judge", tags=("llm", "judge", "crew"))
class CrewJudge(BaseJudge):
    """Adapter that lets any registered :class:`BaseFinancialCrew` act as a judge.

    The crew is invoked once per ``(vt_symbol, ts)`` decision; its
    ``payload`` is mapped onto a :class:`Finding`. Use sparingly — this
    is N times more expensive than :class:`LLMJudge`.
    """

    name = "crew_judge"

    def __init__(
        self,
        crew_class: str = "MarketForecasterCrew",
        crew_kwargs: dict[str, Any] | None = None,
        max_decisions: int = 25,
        cost_budget_usd: float = 5.0,
    ) -> None:
        self.crew_class = crew_class
        self.crew_kwargs = dict(crew_kwargs or {})
        self.max_decisions = max(1, int(max_decisions))
        self.cost_budget_usd = float(cost_budget_usd)

    def _build_crew(self) -> Any:
        from aqp.core.registry import resolve

        cls = resolve(self.crew_class)
        return cls(**self.crew_kwargs)

    def evaluate(
        self,
        decisions: list[dict[str, Any]] | pd.DataFrame,
        equity_curve: pd.Series | None = None,
        *,
        backtest_id: str | None = None,
        bars: pd.DataFrame | None = None,
        rubric: str | None = None,
    ) -> JudgeReport:
        records = _decisions_to_records(decisions)[: self.max_decisions]
        if not records:
            return JudgeReport(
                judge_class=type(self).__name__,
                backtest_id=backtest_id,
                summary="No decisions to evaluate.",
            )
        try:
            crew = self._build_crew()
        except Exception:
            logger.exception("CrewJudge: cannot build crew %s", self.crew_class)
            return JudgeReport(
                judge_class=type(self).__name__,
                backtest_id=backtest_id,
                summary=f"Failed to build crew {self.crew_class}",
            )

        findings: list[Finding] = []
        total_cost = 0.0
        provider = ""
        model = ""
        for rec in records:
            try:
                report = crew.run(
                    ticker=rec["vt_symbol"],
                    as_of=rec["ts"],
                    price_summary={},
                    fundamentals={},
                    news_digest=[
                        {"headline": rec.get("rationale", ""), "summary": rec.get("rationale", "")}
                    ],
                )
            except Exception:
                logger.exception("CrewJudge: crew.run failed for %s", rec.get("vt_symbol"))
                continue
            usage = getattr(report, "usage", {}) or {}
            total_cost += float(usage.get("cost_usd", 0.0) or 0.0)
            providers = usage.get("providers") or [""]
            models = usage.get("models") or [""]
            provider = provider or (providers[0] if providers else "")
            model = model or (models[0] if models else "")
            horizons = (getattr(report, "payload", {}) or {}).get("horizons", []) or []
            primary = horizons[0] if horizons else {}
            direction = str(primary.get("direction", "FLAT")).upper()
            recommended_action: Action
            if direction == "UP":
                recommended_action = "BUY"
            elif direction == "DOWN":
                recommended_action = "SELL"
            else:
                recommended_action = "HOLD"
            verdict: Verdict = (
                "keep" if recommended_action == rec["action"] else "edit"
            )
            findings.append(
                Finding(
                    decision_id=rec.get("decision_id"),
                    vt_symbol=rec["vt_symbol"],
                    ts=rec["ts"],
                    severity=("warn" if verdict == "edit" else "info"),
                    verdict=verdict,
                    recommended_action=recommended_action,
                    recommended_size_pct=float(rec.get("size_pct", 0.0)),
                    rationale=str(primary.get("rationale", ""))[:300],
                )
            )
            if total_cost >= self.cost_budget_usd:
                break

        # Heuristic score: fraction of "keep" verdicts.
        kept = sum(1 for f in findings if f.verdict == "keep")
        score = kept / len(findings) if findings else 0.0
        return JudgeReport(
            judge_class=type(self).__name__,
            backtest_id=backtest_id,
            score=float(score),
            summary=(
                f"Crew judge {self.crew_class}: {kept}/{len(findings)} decisions kept; "
                f"{len(findings) - kept} suggested edits/vetoes."
            ),
            findings=findings,
            cost_usd=round(total_cost, 6),
            provider=provider,
            model=model,
            rubric="crew",
        )


__all__ = [
    "BaseJudge",
    "CrewJudge",
    "Finding",
    "JudgeReport",
    "LLMJudge",
]
