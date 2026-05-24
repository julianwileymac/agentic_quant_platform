"""``StrategyAgentsTool`` — surface other RL agents' decisions for ensemble.

FinAgent's "decision" stage can optionally query other RL agents in
the registry for their preferred action and consider the ensemble
when emitting its own decision. This tool surfaces a single agent's
decision for the LLM to reason over.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


try:
    from crewai.tools import BaseTool  # type: ignore[import-not-found]
except Exception:  # noqa: BLE001

    class BaseTool:  # type: ignore[no-redef]
        name: str = "tool"
        description: str = ""

        def _run(self, *args: Any, **kwargs: Any) -> str:
            raise NotImplementedError


_ACTION_NAMES = {0: "SELL", 1: "HOLD", 2: "BUY"}


class StrategyAgentsTool(BaseTool):
    """Query a registered RL agent for its preferred action."""

    name: str = "strategy_agents_query"
    description: str = (
        "Query a registered RL agent for its preferred action on a "
        "given observation. Returns a string label (SELL/HOLD/BUY). "
        "Input: dict with 'agent_alias' and 'observation_json'."
    )

    def _run(self, payload: dict[str, Any] | str) -> str:
        import json

        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                return "input is not a JSON object"
        alias = str(payload.get("agent_alias", ""))
        observation = payload.get("observation_json")
        if not alias:
            return "missing agent_alias"
        try:
            from aqp.core.registry import build_from_config  # noqa: PLC0415

            agent = build_from_config({"class": alias})
        except Exception:  # noqa: BLE001
            return f"agent {alias} not in registry"
        try:
            action, _ = agent.predict(observation, deterministic=True)
        except Exception:  # noqa: BLE001 — defensive
            return f"agent {alias} predict failed"
        try:
            action_int = int(action)
        except Exception:  # noqa: BLE001
            return str(action)
        return _ACTION_NAMES.get(action_int, str(action_int))


__all__ = ["StrategyAgentsTool"]
