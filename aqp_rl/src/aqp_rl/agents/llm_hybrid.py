"""``LLMHybridAgent`` — FinRobot-style LLM proposes, RL fine-tunes via residual.

Combines a frozen RL policy (any :class:`BaseRLAgent`) with an LLM
advisor that proposes a target weight vector / discrete action from
the env's market state. The adapter blends the two sources by a
configurable ``llm_weight`` (default 0.5) so researchers can study
"LLM-prior" residual policies without baking the LLM call into the
backbone agent.

Hard rule: all LLM calls go through
:func:`aqp.llm.providers.router.router_complete` per the AQP rules
(no direct ``litellm.completion`` / ``OllamaClient`` calls).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, ClassVar

import gymnasium as gym
import numpy as np

from aqp_rl.core.policy import BaseRLAgent

logger = logging.getLogger(__name__)


_DEFAULT_PROMPT = """You are a trading advisor. The current market state vector is:

{state}

The available action space has {action_dim} dimensions. Output a single line of valid
JSON of the form {{"action": [<n_floats_in_-1_to_1>]}}, with no commentary.
"""


class LLMHybridAgent(BaseRLAgent):
    """RL backbone + LLM advisor with weighted blending.

    The backbone (``rl_agent``) handles all training. The advisor only
    runs at inference time when ``llm_weight > 0``.
    """

    rl_alias: ClassVar[str] = "LLMHybridAgent"
    rl_source: ClassVar[str] = "finrobot"
    rl_category: ClassVar[str] = "hybrid"
    rl_tags: ClassVar[tuple[str, ...]] = ("llm", "hybrid", "finrobot")

    algorithm: str = "LLMHybrid"

    def __init__(
        self,
        *,
        rl_agent: BaseRLAgent | dict[str, Any],
        llm_model: str | None = None,
        llm_provider: str | None = None,
        llm_weight: float = 0.5,
        prompt_template: str | None = None,
        max_tokens: int = 200,
        temperature: float = 0.0,
    ) -> None:
        from aqp.core.registry import build_from_config

        if isinstance(rl_agent, dict):
            built = build_from_config(rl_agent)
            if not isinstance(built, BaseRLAgent):
                raise TypeError(
                    f"LLMHybridAgent.rl_agent must be a BaseRLAgent, got {type(built)}"
                )
            self.rl_agent = built
        else:
            self.rl_agent = rl_agent
        self.llm_model = llm_model
        self.llm_provider = llm_provider
        self.llm_weight = float(np.clip(llm_weight, 0.0, 1.0))
        self.prompt_template = prompt_template or _DEFAULT_PROMPT
        self.max_tokens = int(max_tokens)
        self.temperature = float(temperature)
        self._action_dim: int | None = None

    def build(self, env: gym.Env) -> None:
        self.rl_agent.build(env)
        try:
            self._action_dim = int(env.action_space.shape[0]) if env.action_space.shape else int(env.action_space.n)
        except Exception:  # noqa: BLE001
            self._action_dim = 1

    def train(
        self,
        total_timesteps: int,
        callbacks: list[Any] | None = None,
        log_interval: int = 10,
    ) -> None:
        self.rl_agent.train(total_timesteps=total_timesteps, callbacks=callbacks, log_interval=log_interval)

    def save(self, path: str | Path) -> Path:
        return self.rl_agent.save(path)

    def load(self, path: str | Path, env: gym.Env | None = None) -> None:
        self.rl_agent.load(path, env=env)
        if env is not None:
            try:
                self._action_dim = int(env.action_space.shape[0]) if env.action_space.shape else int(env.action_space.n)
            except Exception:  # noqa: BLE001
                pass

    def predict(self, obs: Any, *, deterministic: bool = True) -> Any:
        rl_action, state = self.rl_agent.predict(obs, deterministic=deterministic)
        if self.llm_weight <= 0.0 or self.llm_model is None:
            return rl_action, state
        try:
            llm_action = self._consult_llm(obs)
        except Exception:  # noqa: BLE001
            logger.exception("LLM advisor failed; falling back to RL action")
            return rl_action, state
        try:
            blended = (1.0 - self.llm_weight) * np.asarray(rl_action, dtype=np.float32) + self.llm_weight * np.asarray(llm_action, dtype=np.float32)
        except Exception:  # noqa: BLE001
            return rl_action, state
        return blended, state

    def _consult_llm(self, obs: Any) -> np.ndarray:
        try:
            from aqp.llm.providers.router import router_complete
        except Exception as exc:  # pragma: no cover
            raise ImportError("aqp.llm.providers.router is unavailable") from exc
        prompt = self.prompt_template.format(state=str(np.asarray(obs).tolist()), action_dim=self._action_dim or 1)
        response = router_complete(
            messages=[{"role": "user", "content": prompt}],
            model=self.llm_model,
            provider=self.llm_provider,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        text = ""
        if isinstance(response, dict):
            choices = response.get("choices") or []
            if choices:
                text = choices[0].get("message", {}).get("content") or choices[0].get("text") or ""
            text = text or response.get("content", "")
        else:
            text = str(response)
        try:
            payload = json.loads(text.strip())
        except Exception:
            # Fall back to extracting the first array we see.
            start = text.find("[")
            end = text.rfind("]")
            if start == -1 or end == -1:
                raise ValueError(f"LLM did not return parseable JSON: {text[:120]}")
            payload = {"action": json.loads(text[start : end + 1])}
        action = np.asarray(payload.get("action", []), dtype=np.float32).flatten()
        if self._action_dim and action.size != self._action_dim:
            action = np.resize(action, (self._action_dim,)).astype(np.float32)
        return np.clip(action, -1.0, 1.0)

    @property
    def model(self) -> Any:
        return self.rl_agent.model


__all__ = ["LLMHybridAgent"]
