"""``RLTradingBot`` — bot subtype driven by a trained RL policy.

Phase 8 of the hybrid agentic-RL rollout. The bot composes
:class:`aqp.rl.runtime.RLRuntime` (rule 16, the only sanctioned RL
executor) so its ``backtest`` / ``paper`` / ``deploy`` lifecycle
methods route through the RL stack instead of through
``run_backtest_from_config`` / ``build_session_from_config``.

Spec contract
-------------

An :class:`RLTradingBot` requires :attr:`BotSpec.rl_experiment_ref`
to point at a registered :class:`RLExperimentSpec`. The spec's
``strategy`` / ``backtest`` blocks are optional — when present
they're used as overrides for the RL env (e.g. to override the
initial cash or transaction cost in the underlying
:class:`RLBacktestEnv`).

Lifecycle
---------

- ``backtest()`` → ``RLRuntime.train()`` or ``RLRuntime.evaluate()``
  depending on whether a checkpoint is supplied.
- ``paper()`` → ``RLRuntime.paper(checkpoint=...)`` against the
  configured live broker.
- ``chat()`` → unsupported (matches :class:`TradingBot`).
- ``deploy()`` → routes through the standard
  :class:`DeploymentDispatcher` so the deployment target
  (paper_session / kubernetes / backtest_only) doesn't have to know
  about RL.

The bot NEVER imports ``aqp.rl.agents.*`` directly — it composes
``RLRuntime`` only, which handles env / agent / advantage / trajectory
store assembly under the hood (preserves rule 16).
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.bots.base import BaseBot, BotMethodNotSupported
from aqp.bots.spec import BotSpec
from aqp.core.registry import register

logger = logging.getLogger(__name__)


@register("RLTradingBot", kind="bot", tags=("bot", "rl_trading", "agentic_rl"))
class RLTradingBot(BaseBot):
    """Bot subtype that routes lifecycle through :class:`RLRuntime`."""

    kind: str = "rl_trading"

    def __init__(
        self,
        *,
        spec: BotSpec,
        bot_id: str | None = None,
        project_id: str | None = None,
    ) -> None:
        if spec.rl_experiment_ref is None:
            raise ValueError(
                f"RLTradingBot {spec.name!r} requires spec.rl_experiment_ref (got None)"
            )
        super().__init__(spec=spec, bot_id=bot_id, project_id=project_id)

    # ------------------------------------------------------------------ lifecycle

    def backtest(self, *, run_name: str | None = None, **overrides: Any) -> dict[str, Any]:
        """Drive ``RLRuntime.train()`` or ``evaluate()``.

        If the spec carries a checkpoint we evaluate; otherwise we
        train from scratch. Either way the returned dict is the
        :class:`RLRunResult.to_dict()` payload so the calling code
        (Celery task, route) gets a uniform shape.
        """
        runtime = self._runtime()
        ref = self.spec.rl_experiment_ref
        if ref is not None and ref.checkpoint:
            outcome = runtime.evaluate(checkpoint=str(ref.checkpoint), overrides=overrides or None)
        else:
            outcome = runtime.train(run_name=run_name, overrides=overrides or None)
        return outcome.to_dict() if hasattr(outcome, "to_dict") else {"value": str(outcome)}

    def paper(self, *, run_name: str | None = None, **overrides: Any) -> Any:
        """Drive ``RLRuntime.paper(checkpoint=...)``.

        Requires the spec to carry a checkpoint. Returns the
        :class:`RLRunResult` (not pre-converted) so the calling code
        can introspect richer fields.
        """
        runtime = self._runtime()
        ref = self.spec.rl_experiment_ref
        if ref is None or not ref.checkpoint:
            raise BotMethodNotSupported(
                f"RLTradingBot {self.spec.name!r} cannot paper-trade without a "
                "checkpoint on rl_experiment_ref"
            )
        return runtime.paper(checkpoint=str(ref.checkpoint), overrides=overrides or None)

    def chat(
        self,
        prompt: str,
        *,
        session_id: str | None = None,
        agent_role: str | None = None,
        **kwargs: Any,
    ) -> Any:
        raise BotMethodNotSupported(
            "RLTradingBot does not support chat(); pair it with a ResearchBot "
            "or expose the StrategyExecutor agent."
        )

    # ------------------------------------------------------------------ helpers

    def _runtime(self) -> Any:
        from aqp.rl.registry import get_rl_spec
        from aqp.rl.runtime import RLRuntime

        ref = self.spec.rl_experiment_ref
        assert ref is not None  # enforced in __init__
        rl_spec = get_rl_spec(ref.slug)
        runtime = RLRuntime(rl_spec)
        return runtime


__all__ = ["RLTradingBot"]
