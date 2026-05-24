"""``RLAgentBridge`` — single channel exposed via ``context['rl_agent']``.

Mirrors the API surface of
:class:`aqp.strategies.agentic.agent_dispatcher.AgentDispatcher` so a
strategy can call ``context['rl_agent'].consult(obs)`` exactly like it
calls ``context['agents'].consult("research.signal", inputs={...})``.
The bridge is deliberately thin: it owns the trained policy, runs the
:class:`WeightCentricPipeline` (FinRL-X ``f_S -> f_A -> f_T -> f_R``),
and stamps the last decision on ``last_decision`` so observers (the
event log, the trajectory store) can pick it up.

Typical wiring inside :class:`RLBacktestEnv`:

    bridge = RLAgentBridge(policy=trained_policy, pipeline=pipeline)
    backtest_engine.attach_rl_agent(bridge)

The engine then injects ``context['rl_agent'] = bridge`` on every
bar; strategy code calls ``bridge.consult(obs)`` to pull the next
target-weight vector.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class RLDecision:
    """Single decision emitted by an :class:`RLAgentBridge`.

    Carries the target-weight vector plus the raw policy action plus
    the :class:`PipelineState` (universe / per-stage weight history)
    so audit consumers can reconstruct the FinRL-X four-stage trace
    later — useful for both the RL Lab UI and the ``LedgerWriter``
    persistence path.
    """

    target_weights: dict[str, float] = field(default_factory=dict)
    raw_action: Any | None = None
    pipeline_state: Any | None = None
    timestamp: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_weight_array(self) -> np.ndarray:
        return np.asarray(list(self.target_weights.values()), dtype=np.float64)


class RLAgentBridge:
    """Wraps a trained policy + a :class:`WeightCentricPipeline`.

    Mirrors the AgentDispatcher API so a strategy can ``consult`` the
    bridge with the current observation and receive an
    :class:`RLDecision`. The bridge ALSO stores the most recent
    decision on :attr:`last_decision` so an engine that does not want
    to invoke the bridge directly can poll it after each bar.
    """

    def __init__(
        self,
        *,
        policy: Any,
        pipeline: Any,
        universe: list[str] | None = None,
        deterministic: bool = True,
    ) -> None:
        if policy is None:
            raise ValueError("RLAgentBridge requires a trained policy")
        if pipeline is None:
            raise ValueError("RLAgentBridge requires a WeightCentricPipeline")
        self.policy = policy
        self.pipeline = pipeline
        self.universe = list(universe or [])
        self.deterministic = bool(deterministic)
        self.last_decision: RLDecision | None = None
        self._call_count: int = 0

    # ------------------------------------------------------------------ public

    def consult(
        self,
        observation: Any,
        *,
        inputs: dict[str, Any] | None = None,
        timestamp: Any | None = None,
        universe: list[str] | None = None,
    ) -> RLDecision:
        """Run the policy on ``observation`` and return an :class:`RLDecision`.

        ``inputs`` mirrors the AgentDispatcher signature for
        compatibility with code that already calls
        ``context['agents'].consult(spec_name, inputs={...})``. The
        bridge ignores the spec name (there is only one policy per
        bridge); it does pass ``inputs`` straight into the pipeline
        context so the ``f_S`` / ``f_T`` / ``f_R`` stages can read
        per-bar liquidity / turbulence / regime values.
        """
        action = self._predict(observation)
        ctx = dict(inputs or {})
        if timestamp is not None:
            ctx["current_time"] = timestamp
        universe_eff = list(universe) if universe is not None else list(self.universe)
        state = self.pipeline.run(
            universe=universe_eff,
            raw_action=action,
            context=ctx,
        )
        weights = {
            sym: float(state.weights[i])
            for i, sym in enumerate(state.universe)
            if state.weights is not None and i < len(state.weights)
        }
        decision = RLDecision(
            target_weights=weights,
            raw_action=action,
            pipeline_state=state,
            timestamp=timestamp,
            metadata={
                "call": self._call_count,
                "history": [stage for stage, _ in state.history],
            },
        )
        self.last_decision = decision
        self._call_count += 1
        return decision

    async def consult_async(self, *args: Any, **kwargs: Any) -> RLDecision:
        """Async passthrough so the bridge satisfies the AgentDispatcher protocol."""
        return self.consult(*args, **kwargs)

    # ------------------------------------------------------------------ helpers

    def _predict(self, observation: Any) -> Any:
        """Adapt the observation to whatever signature the policy expects."""
        try:
            # SB3 / CleanRL / RLlib all expose ``predict(obs, deterministic=...)``
            return self.policy.predict(observation, deterministic=self.deterministic)[0]
        except TypeError:
            try:
                return self.policy.predict(observation)
            except Exception:
                logger.exception("RLAgentBridge: policy.predict failed; returning zero action")
                return np.zeros(len(self.universe) or 1, dtype=np.float32)
        except AttributeError:
            try:
                return self.policy(observation)
            except Exception:
                logger.exception("RLAgentBridge: policy callable invocation failed")
                return np.zeros(len(self.universe) or 1, dtype=np.float32)

    def reset(self) -> None:
        self.last_decision = None
        self._call_count = 0


class NoopRLAgentBridge:
    """Fallback bridge returning empty decisions.

    Used when an engine flips ``supports_rl_injection=True`` but no
    trained policy is bound at runtime (e.g. a non-RL strategy
    ignoring ``context['rl_agent']``). Mirrors the
    :class:`_NoopDispatcher` pattern from the event-driven engine.
    """

    def consult(self, *args: Any, **kwargs: Any) -> RLDecision:
        return RLDecision()

    async def consult_async(self, *args: Any, **kwargs: Any) -> RLDecision:
        return RLDecision()

    def reset(self) -> None:
        return None

    @property
    def last_decision(self) -> RLDecision | None:
        return None


__all__ = [
    "NoopRLAgentBridge",
    "RLAgentBridge",
    "RLDecision",
]
