"""``AlphaResearcher`` — drives the FinRL-X factor-mining loop.

Composes :class:`aqp.agents.runtime.AgentRuntime` (the canonical
LLM-driven agent runtime, rule 12) with the symbolic-alpha AST
sandbox (:mod:`aqp.data.expressions_dsl`) and a deterministic
backtest reward.

Lifecycle of one iteration::

    AgentRuntime.run(inputs={"intent": ...})
        -> emits JSON {"name", "formula", "rationale", ...}
    AlphaResearcher.evaluate(...)
        -> compile_to_factor_node(formula)
        -> EventDrivenBacktester.run(<wrapper strategy>)
        -> Sharpe / IR / max-drawdown from BacktestResult
    AlphaResearcher.score_to_reward(metrics)
        -> scalar reward fed back to the agent's next iteration

The agent NEVER imports ORM models, NEVER calls ``router_complete``
directly, and NEVER bypasses the AST sandbox. Compilation failures
are explicitly converted into scalar penalties so the agent learns
to author DSL-compliant formulas through reinforcement.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from aqp.data.expressions_dsl import (
    FactorNode,
    SymbolicAlphaError,
    compile_to_factor_node,
)

logger = logging.getLogger(__name__)


@dataclass
class AlphaResearcherResult:
    """Outcome of one Alpha Researcher iteration."""

    name: str
    formula: str
    rationale: str
    compiled: bool
    factor_node: FactorNode | None = field(default=None, repr=False)
    metrics: dict[str, float] = field(default_factory=dict)
    reward: float = 0.0
    rejection_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out.pop("factor_node", None)
        return out


class AlphaResearcher:
    """High-level driver that wraps :class:`AgentRuntime` for factor mining.

    Parameters
    ----------
    agent_spec_name:
        Slug of the registered :class:`AgentSpec` (default
        ``"alpha_researcher"`` — the spec in
        ``configs/agents/alpha_researcher.yaml``).
    backtest_engine:
        Concrete :class:`aqp.backtest.base.BaseBacktestEngine`
        instance for offline reward computation. Defaults to a
        fresh :class:`EventDrivenBacktester` so the agent runs
        hermetically without extra config.
    compile_penalty:
        Scalar reward returned when the LLM emits a formula that
        fails AST validation. Defaults to ``-1.0`` so the agent
        learns to avoid the DSL violations after a handful of
        retries.
    duplicate_penalty:
        Scalar reward returned when the agent re-proposes a formula
        already seen in this session. Default ``-0.25``.
    """

    def __init__(
        self,
        *,
        agent_spec_name: str = "alpha_researcher",
        backtest_engine: Any | None = None,
        compile_penalty: float = -1.0,
        duplicate_penalty: float = -0.25,
    ) -> None:
        self.agent_spec_name = str(agent_spec_name)
        self._engine = backtest_engine
        self.compile_penalty = float(compile_penalty)
        self.duplicate_penalty = float(duplicate_penalty)
        self._seen_formulas: set[str] = set()

    # ------------------------------------------------------------------ public

    def propose(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Drive :class:`AgentRuntime` once and return the parsed proposal.

        Returns a dict with at minimum
        ``{"name", "formula", "rationale"}`` even when the LLM output
        cannot be parsed — the wrapper falls back to a heuristic
        default so the evaluation loop can still produce a reward
        (penalty) and the agent can self-correct on the next iteration.
        """
        from aqp.agents.runtime import AgentRuntime
        from aqp.agents.registry import get_agent_spec

        spec = get_agent_spec(self.agent_spec_name)
        runtime = AgentRuntime(spec)
        result = runtime.run(inputs=inputs)
        raw = (result.get("output") if isinstance(result, dict) else None) or {}
        parsed = self._coerce_proposal(raw)
        return parsed

    def evaluate(
        self,
        proposal: dict[str, Any],
        *,
        bars,
        sharpe_weight: float = 1.0,
        drawdown_weight: float = 0.5,
        turnover_weight: float = 0.2,
    ) -> AlphaResearcherResult:
        """Compile + backtest the proposal and compute a scalar reward.

        Backtest evaluation goes through a thin
        :class:`_FactorStrategyShim` so the same factor compiles into
        an executable signal for the event-driven engine. Sharpe + IR
        + drawdown weights tune the reward — defaults emphasise
        risk-adjusted return over raw PnL.
        """
        name = str(proposal.get("name") or "alpha")
        formula = str(proposal.get("formula") or "").strip()
        rationale = str(proposal.get("rationale") or "")
        if not formula:
            return AlphaResearcherResult(
                name=name,
                formula="",
                rationale=rationale,
                compiled=False,
                reward=self.compile_penalty,
                rejection_reason="empty_formula",
            )
        if formula in self._seen_formulas:
            return AlphaResearcherResult(
                name=name,
                formula=formula,
                rationale=rationale,
                compiled=False,
                reward=self.duplicate_penalty,
                rejection_reason="duplicate_formula",
            )
        try:
            factor = compile_to_factor_node(formula, name=name)
        except SymbolicAlphaError as exc:
            return AlphaResearcherResult(
                name=name,
                formula=formula,
                rationale=rationale,
                compiled=False,
                reward=self.compile_penalty,
                rejection_reason=str(exc),
            )
        self._seen_formulas.add(formula)

        engine = self._engine or self._default_engine()
        metrics = self._backtest_factor(engine, factor, bars)
        reward = self.score_to_reward(
            metrics,
            sharpe_weight=sharpe_weight,
            drawdown_weight=drawdown_weight,
            turnover_weight=turnover_weight,
        )
        return AlphaResearcherResult(
            name=name,
            formula=formula,
            rationale=rationale,
            compiled=True,
            factor_node=factor,
            metrics=metrics,
            reward=reward,
        )

    def score_to_reward(
        self,
        metrics: dict[str, float],
        *,
        sharpe_weight: float = 1.0,
        drawdown_weight: float = 0.5,
        turnover_weight: float = 0.2,
    ) -> float:
        sharpe = float(metrics.get("sharpe", 0.0) or 0.0)
        mdd = float(metrics.get("max_drawdown", 0.0) or 0.0)
        turnover = float(metrics.get("turnover", 0.0) or 0.0)
        # Higher Sharpe is better; deeper drawdown (more negative)
        # is worse; higher turnover is worse (transaction cost proxy).
        return sharpe_weight * sharpe + drawdown_weight * mdd - turnover_weight * abs(turnover)

    # ------------------------------------------------------------------ helpers

    def _coerce_proposal(self, raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except Exception:
                return {"formula": raw, "name": "raw", "rationale": ""}
        return {"name": "anon", "formula": "", "rationale": ""}

    def _default_engine(self) -> Any:
        try:
            from aqp.backtest.engine import EventDrivenBacktester

            return EventDrivenBacktester(initial_cash=100_000.0)
        except Exception:
            logger.exception("Failed to construct default EventDrivenBacktester")
            return None

    def _backtest_factor(self, engine: Any, factor: FactorNode, bars) -> dict[str, float]:
        from aqp.agents.quant.factor_strategy_shim import FactorStrategyShim

        if engine is None or bars is None:
            return {}
        strategy = FactorStrategyShim(factor=factor)
        try:
            result = engine.run(strategy, bars)
        except Exception:
            logger.exception("Backtest evaluation of factor %r failed", factor.formula)
            return {}
        # BacktestResult.summary is a dict with keys like ``sharpe``,
        # ``max_drawdown``, ``total_return``, ``turnover``.
        summary = getattr(result, "summary", None) or {}
        if not isinstance(summary, dict):
            return {}
        return {
            "sharpe": float(summary.get("sharpe", 0.0) or 0.0),
            "max_drawdown": float(summary.get("max_drawdown", 0.0) or 0.0),
            "total_return": float(summary.get("total_return", 0.0) or 0.0),
            "turnover": float(summary.get("turnover", 0.0) or 0.0),
        }


__all__ = ["AlphaResearcher", "AlphaResearcherResult"]
