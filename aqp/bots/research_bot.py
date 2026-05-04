"""Research-focused bot subclass.

A :class:`ResearchBot` requires at least one agent in its spec; the
chat surface dispatches each turn through :class:`AgentRuntime` so all
RAG retrievals, memory bindings, and guardrails apply uniformly. The
bot can also run an on-demand backtest if the spec supplies a
``strategy`` block — useful for "ask the bot to test this idea" UX.

Paper trading is intentionally disabled by default; if a user wants to
turn a research thesis into a live bot they should clone the spec into
a :class:`TradingBot`.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from aqp.bots.base import BaseBot, BotMethodNotSupported
from aqp.bots.spec import BotAgentRef, BotSpec
from aqp.core.registry import register

logger = logging.getLogger(__name__)


@register("ResearchBot", kind="bot", tags=("bot", "research", "chat"))
class ResearchBot(BaseBot):
    """Bot subtype with a chat surface backed by spec-driven agents."""

    kind: str = "research"

    def __init__(
        self,
        *,
        spec: BotSpec,
        bot_id: str | None = None,
        project_id: str | None = None,
    ) -> None:
        if not spec.agents:
            raise ValueError(
                f"ResearchBot {spec.name!r} requires at least one agent on spec.agents"
            )
        super().__init__(spec=spec, bot_id=bot_id, project_id=project_id)

    # ------------------------------------------------------------------ chat

    def chat(
        self,
        prompt: str,
        *,
        session_id: str | None = None,
        agent_role: str | None = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Drive a single chat turn through the configured agent specs.

        - When ``agent_role`` is supplied, only agents matching that role
          run. Otherwise every enabled agent on the spec runs and the
          payloads are merged into a single dict keyed by spec name.
        - Each agent receives ``{prompt, ...ref.inputs_template, ...caller_inputs}``
          and is executed via :class:`AgentRuntime` so RAG / memory /
          guardrails behave identically to direct ``/agents/runs/v2/sync``
          calls.
        """
        from aqp.agents.registry import get_agent_spec
        from aqp.agents.runtime import AgentRuntime

        merged_inputs = {"prompt": prompt}
        if isinstance(inputs, dict):
            merged_inputs.update(inputs)

        replies: dict[str, Any] = {}
        for ref in self._select_agents(agent_role):
            try:
                agent_spec = get_agent_spec(ref.spec_name)
            except KeyError:
                logger.warning("ResearchBot.chat: unknown agent spec %s", ref.spec_name)
                continue
            agent_inputs = {**(ref.inputs_template or {}), **merged_inputs}
            result = AgentRuntime(agent_spec, session_id=session_id).run(agent_inputs)
            replies[ref.spec_name] = result.to_dict()

        return {
            "bot_slug": self.spec.slug,
            "bot_kind": self.spec.kind,
            "session_id": session_id,
            "prompt": prompt,
            "agent_role": agent_role,
            "replies": replies,
            "summary": _format_summary(replies),
        }

    # ------------------------------------------------------------------ backtest gate

    def backtest(self, *, run_name: str | None = None, **overrides: Any) -> dict[str, Any]:
        """Allow on-demand backtests only when the spec carries strategy/backtest blocks."""
        if self.spec.strategy is None or self.spec.backtest is None:
            raise BotMethodNotSupported(
                "ResearchBot.backtest() requires both strategy and backtest blocks "
                "on the spec; this bot is research-only."
            )
        return super().backtest(run_name=run_name, **overrides)

    def paper(self, *, run_name: str | None = None, **overrides: Any) -> Any:
        raise BotMethodNotSupported(
            "ResearchBot does not paper-trade; clone the spec into a TradingBot first."
        )

    # ------------------------------------------------------------------ helpers

    def _select_agents(self, role: str | None) -> list[BotAgentRef]:
        if role:
            return [a for a in self.spec.agents if a.enabled and a.role == role]
        return [a for a in self.spec.agents if a.enabled]


def _format_summary(replies: dict[str, Any]) -> str:
    """Concise text summary for UI rendering."""
    if not replies:
        return "(no agent replies)"
    chunks: list[str] = []
    for name, payload in replies.items():
        output = payload.get("output", {}) if isinstance(payload, dict) else {}
        text = ""
        if isinstance(output, dict):
            text = (
                output.get("text")
                or output.get("summary")
                or output.get("rationale")
                or json.dumps(output, default=str)[:600]
            )
        else:
            text = str(output)[:600]
        chunks.append(f"### {name}\n{text}")
    return "\n\n".join(chunks)


__all__ = ["ResearchBot"]
