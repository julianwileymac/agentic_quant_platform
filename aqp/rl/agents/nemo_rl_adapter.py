"""``NeMoRLAdapter`` — optional NVIDIA NeMo-RL adapter (parity).

Wraps :mod:`nemo_rl.algorithms.grpo` so users with the NeMo-RL stack
installed can drive a NeMo policy through :class:`RLRuntime` (rule 16)
exactly like any other :class:`BaseRLAgent` adapter.

The native AQP advantage estimators in :mod:`aqp.rl.advantage`
(:class:`ReinforcePlusPlusAdvantage`, :class:`GRPOAdvantage`) port the
key NeMo-RL math without the heavy dependency footprint — most users
should prefer those. This adapter exists as the full-fidelity option
for users who already run the NeMo-RL stack.

Same import-guard pattern as the existing
:class:`ElegantRLAdapter` / :class:`RayRLlibAdapter` /
:class:`CleanRLAdapter` adapters — the class still imports and
registers, but raises a clear :class:`ImportError` on ``build()``
when ``nemo_rl`` is not installed.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, ClassVar

import gymnasium as gym

from aqp.rl.core.policy import BaseRLAgent

logger = logging.getLogger(__name__)


try:
    import nemo_rl  # type: ignore[import]

    _NEMO_AVAILABLE = True
except Exception:
    nemo_rl = None  # type: ignore[assignment]
    _NEMO_AVAILABLE = False


class NeMoRLAdapter(BaseRLAgent):
    """Optional NVIDIA NeMo-RL adapter (full-fidelity GRPO / PPO).

    Parameters
    ----------
    algorithm:
        ``"grpo"`` (default) | ``"ppo"`` | ``"reinforce_plus_plus"``.
    config:
        Free-form dict passed to the underlying NeMo-RL algorithm
        constructor. Refer to the NeMo-RL YAML schema for the full
        knob list; defaults are kept here intentionally sparse.
    """

    rl_alias: ClassVar[str] = "NeMoRLAdapter"
    rl_source: ClassVar[str] = "nemo_rl"
    rl_category: ClassVar[str] = "drl"
    rl_tags: ClassVar[tuple[str, ...]] = ("nemo_rl", "grpo", "reinforce_plus_plus", "optional_dep")

    def __init__(
        self,
        *,
        algorithm: str = "grpo",
        config: dict[str, Any] | None = None,
    ) -> None:
        self.algorithm = str(algorithm).lower()
        self.config: dict[str, Any] = dict(config or {})
        self._model: Any | None = None

    def build(self, env: gym.Env) -> None:
        if not _NEMO_AVAILABLE:
            raise ImportError(
                "NeMoRLAdapter requires the optional `nemo_rl` package. "
                "Install via the NVIDIA-NeMo/RL repo. For the lean alternative "
                "use `aqp.rl.advantage.ReinforcePlusPlusAdvantage` (native port)."
            )
        if self.algorithm == "grpo":
            from nemo_rl.algorithms import grpo  # type: ignore[import]

            self._model = grpo.GRPO(env=env, **self.config)
        else:
            raise NotImplementedError(
                f"NeMoRLAdapter: algorithm={self.algorithm!r} not yet bridged. "
                "Supported: 'grpo'. PRs welcome."
            )

    def train(
        self,
        total_timesteps: int,
        callbacks: list[Any] | None = None,
        log_interval: int = 10,
    ) -> None:
        if self._model is None:
            raise RuntimeError("NeMoRLAdapter not built. Call .build(env) first.")
        if hasattr(self._model, "train"):
            self._model.train(total_timesteps=int(total_timesteps))
        elif hasattr(self._model, "learn"):
            self._model.learn(total_timesteps=int(total_timesteps))
        else:
            raise NotImplementedError(
                "NeMoRLAdapter: bound model has no .train/.learn method"
            )

    def save(self, path: str | Path) -> Path:
        if self._model is None:
            raise RuntimeError("NeMoRLAdapter has no model to save")
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if hasattr(self._model, "save"):
            self._model.save(p.as_posix())
        return p

    def load(self, path: str | Path, env: gym.Env | None = None) -> None:
        if not _NEMO_AVAILABLE:
            raise ImportError("nemo_rl not available")
        if hasattr(self._model, "load"):
            self._model.load(str(path))

    def predict(self, obs: Any, *, deterministic: bool = True) -> Any:
        if self._model is None:
            raise RuntimeError("NeMoRLAdapter has no model loaded")
        if hasattr(self._model, "predict"):
            return self._model.predict(obs, deterministic=deterministic)
        if hasattr(self._model, "act"):
            return self._model.act(obs)
        raise NotImplementedError("NeMoRLAdapter: bound model has no .predict/.act")

    @property
    def model(self) -> Any:
        return self._model


__all__ = ["NeMoRLAdapter"]
