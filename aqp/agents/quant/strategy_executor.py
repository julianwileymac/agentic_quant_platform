"""``StrategyExecutor`` — dispatch wrapper around :class:`RLRuntime`.

Drives the four RL lifecycle actions (train / evaluate / paper /
replay) on behalf of the human portfolio manager. The agent's LLM
output is a JSON ``action`` payload (see
``configs/agents/strategy_executor.yaml``) which this wrapper
translates into the matching :class:`RLRuntime` call.

This module NEVER imports ORM models — it reads RL spec metadata
via :func:`aqp.rl.registry.get_rl_spec` (which is the canonical
factory) and writes lifecycle telemetry through the runtime alone.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class StrategyExecutorResult:
    """Outcome of one Strategy Executor iteration."""

    intent: str
    experiment_slug: str
    rationale: str
    go: bool
    runtime_result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_INTENT_HANDLERS: dict[str, str] = {
    "train": "train",
    "evaluate": "evaluate",
    "paper": "paper",
    "replay": "replay",
    "walk_forward": "walk_forward",
}


class StrategyExecutor:
    """Bridges :class:`AgentRuntime` output into :class:`RLRuntime` calls.

    Parameters
    ----------
    agent_spec_name:
        Slug of the registered :class:`AgentSpec` (default
        ``"strategy_executor"``). The spec lives in
        ``configs/agents/strategy_executor.yaml``.
    require_kill_switch_clear:
        When ``True`` (default) any paper / live intent is aborted
        if the global kill switch is engaged.
    """

    def __init__(
        self,
        *,
        agent_spec_name: str = "strategy_executor",
        require_kill_switch_clear: bool = True,
    ) -> None:
        self.agent_spec_name = str(agent_spec_name)
        self.require_kill_switch_clear = bool(require_kill_switch_clear)

    def decide_and_run(self, inputs: dict[str, Any]) -> StrategyExecutorResult:
        from aqp.agents.runtime import AgentRuntime
        from aqp.agents.registry import get_agent_spec

        spec = get_agent_spec(self.agent_spec_name)
        runtime = AgentRuntime(spec)
        result = runtime.run(inputs=inputs)
        # Defect 6 fix: ``AgentRuntime.run`` returns an
        # :class:`AgentRunResult` dataclass; ``isinstance(result, dict)``
        # was always False so the wrapper used to return ``{}`` every
        # call. Read ``result.output`` directly.
        if hasattr(result, "output"):
            raw = dict(getattr(result, "output", None) or {}) if getattr(
                result, "status", "completed"
            ) == "completed" else {}
        elif isinstance(result, dict):
            raw = dict(result.get("output") or {})
        else:
            raw = {}
        action = self._coerce_action(raw, fallback_intent=str(inputs.get("intent") or ""))
        intent = action.get("intent") or ""
        slug = action.get("experiment_slug") or ""
        rationale = action.get("rationale") or ""
        go = bool(action.get("go", True))
        window = action.get("window") or {}

        # Kill-switch gating before any paper / live action.
        if go and intent == "paper" and self.require_kill_switch_clear and self._kill_switch_engaged():
            return StrategyExecutorResult(
                intent=intent,
                experiment_slug=slug,
                rationale=rationale or "Kill switch engaged",
                go=False,
                runtime_result={},
                error="kill_switch_engaged",
            )

        if not go:
            return StrategyExecutorResult(
                intent=intent,
                experiment_slug=slug,
                rationale=rationale,
                go=False,
                runtime_result={},
            )

        handler = _INTENT_HANDLERS.get(intent)
        if handler is None:
            return StrategyExecutorResult(
                intent=intent,
                experiment_slug=slug,
                rationale=rationale,
                go=False,
                runtime_result={},
                error=f"unknown_intent:{intent}",
            )
        try:
            rl_result = self._dispatch(handler, slug=slug, window=window)
        except Exception as exc:
            logger.exception("StrategyExecutor: %s on %s failed", handler, slug)
            return StrategyExecutorResult(
                intent=intent,
                experiment_slug=slug,
                rationale=rationale,
                go=True,
                runtime_result={},
                error=str(exc),
            )
        return StrategyExecutorResult(
            intent=intent,
            experiment_slug=slug,
            rationale=rationale,
            go=True,
            runtime_result=rl_result,
        )

    # ------------------------------------------------------------------ helpers

    def _coerce_action(self, raw: Any, *, fallback_intent: str) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except Exception:
                return {"intent": fallback_intent, "experiment_slug": "", "go": False, "rationale": raw}
        return {"intent": fallback_intent, "experiment_slug": "", "go": False, "rationale": ""}

    def _kill_switch_engaged(self) -> bool:
        try:
            from aqp.risk.kill_switch import is_engaged

            return bool(is_engaged())
        except Exception:
            logger.debug("kill switch probe failed; defaulting to disengaged", exc_info=True)
            return False

    def _dispatch(self, handler: str, *, slug: str, window: dict[str, Any]) -> dict[str, Any]:
        from aqp.rl.registry import get_rl_spec
        from aqp.rl.runtime import RLRuntime

        spec = get_rl_spec(slug)
        runtime = RLRuntime(spec)
        method = getattr(runtime, handler)
        kwargs: dict[str, Any] = {}
        if handler == "evaluate":
            kwargs.update(
                overrides=(
                    {"env": {"kwargs": {"start": window.get("start"), "end": window.get("end")}}}
                    if window
                    else None
                ),
                checkpoint=str(window.get("checkpoint", "")) if window else "",
            )
        elif handler == "paper":
            kwargs.update(checkpoint=str(window.get("checkpoint", "")) if window else "")
        elif handler == "replay":
            kwargs.update(
                checkpoint=str(window.get("checkpoint", "")) if window else "",
                new_window=window or {},
            )
        outcome = method(**{k: v for k, v in kwargs.items() if v not in (None, "")})
        if hasattr(outcome, "to_dict"):
            return outcome.to_dict()
        return {"value": str(outcome)}


__all__ = ["StrategyExecutor", "StrategyExecutorResult"]
