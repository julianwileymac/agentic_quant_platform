"""Trading-focused bot subclass.

A :class:`TradingBot` always carries a ``strategy`` and ``backtest``
block on its spec; it can be backtested, paper-traded, and deployed.
Optional ``agents`` clauses run as supervisors / per-bar advisors via
the existing :class:`aqp.strategies.agentic.agent_dispatcher.AgentDispatcher`
when the underlying engine supports per-bar Python (event-driven).

Chat is intentionally disabled for trading bots — point the user at a
companion :class:`ResearchBot` (or the legacy ``/chat`` endpoint) for
free-form Q&A.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.bots.base import BaseBot, BotMethodNotSupported
from aqp.bots.spec import BotSpec
from aqp.core.registry import register

logger = logging.getLogger(__name__)


@register("TradingBot", kind="bot", tags=("bot", "trading"))
class TradingBot(BaseBot):
    """Bot subtype for live / paper / backtest trading."""

    kind: str = "trading"

    def __init__(
        self,
        *,
        spec: BotSpec,
        bot_id: str | None = None,
        project_id: str | None = None,
    ) -> None:
        if spec.strategy is None:
            raise ValueError(
                f"TradingBot {spec.name!r} requires spec.strategy (got None)"
            )
        if spec.backtest is None:
            raise ValueError(
                f"TradingBot {spec.name!r} requires spec.backtest (got None)"
            )
        super().__init__(spec=spec, bot_id=bot_id, project_id=project_id)

    # -------------------------------------------------------------- chat

    def chat(
        self,
        prompt: str,
        *,
        session_id: str | None = None,
        agent_role: str | None = None,
        **kwargs: Any,
    ) -> Any:
        raise BotMethodNotSupported(
            "TradingBot does not support chat(); pair it with a ResearchBot "
            "or use the legacy /chat endpoint."
        )

    # ----------------------------------------------------- agent advisors

    def consult_agents(
        self,
        prompt: str,
        *,
        inputs: dict[str, Any] | None = None,
        roles: list[str] | None = None,
    ) -> dict[str, Any]:
        """Synchronously call every agent declared on the spec.

        Returns ``{spec_name: AgentRunResult.to_dict()}``. All calls go
        through :class:`AgentRuntime` (the only sanctioned path); the
        bot itself never invokes ``router_complete``.
        """
        from aqp.agents.registry import get_agent_spec
        from aqp.agents.runtime import AgentRuntime

        outputs: dict[str, Any] = {}
        wanted_roles = set(roles) if roles else None
        for ref in self.spec.agents:
            if not ref.enabled:
                continue
            if wanted_roles and ref.role not in wanted_roles:
                continue
            try:
                agent_spec = get_agent_spec(ref.spec_name)
            except KeyError:
                logger.warning("TradingBot.consult_agents: unknown agent spec %s", ref.spec_name)
                continue
            agent_inputs = {**(ref.inputs_template or {}), **(inputs or {}), "prompt": prompt}
            result = AgentRuntime(agent_spec).run(agent_inputs)
            outputs[ref.spec_name] = result.to_dict()
        return outputs


__all__ = ["TradingBot"]
