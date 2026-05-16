"""mbt_gym ↔ AQP RLRuntime adapter.

`mbt_gym <https://github.com/JJJerome/mbt_gym>`_ ships a curated set of
gym environments for model-based limit-order-book trading (Avellaneda-
Stoikov, Cartea-Jaimungal, multi-asset extensions, etc.). This adapter
wraps any mbt_gym env in an AQP :class:`RLComponent` so it slots into
the existing :class:`RLRuntime` lifecycle, telemetry, and Iceberg
trajectory persistence.

Usage::

    from aqp.rl.envs.mbtgym_adapter import MbtGymAdapterEnv

    env = MbtGymAdapterEnv(
        mbtgym_env="TradingEnvironment",
        mbtgym_kwargs={"terminal_time": 1.0, "n_steps": 100},
    )

    # Now drive through RLRuntime / SB3 / etc.
    runtime = RLRuntime(spec).train(env=env, ...)

The adapter intentionally exposes a thin pass-through ``step`` /
``reset`` so all mbt_gym semantics survive intact. The ``info`` dict
gets stamped with an ``"mbtgym"`` flag so downstream reward terms can
opt into the underlying env's bookkeeping (e.g. inventory, midprice).
"""
from __future__ import annotations

import logging
from typing import Any, ClassVar

import gymnasium as gym
import numpy as np

from aqp.rl.core.base import RL_KIND_ENV, RLComponent

logger = logging.getLogger(__name__)


class MbtGymAdapterEnv(gym.Env, RLComponent):
    """Thin adapter around any mbt_gym Gym env."""

    rl_kind: ClassVar[str] = RL_KIND_ENV
    rl_alias: ClassVar[str] = "MbtGymAdapterEnv"
    rl_source: ClassVar[str] = "mbt_gym"
    rl_category: ClassVar[str] = "market-making"
    rl_tags: ClassVar[tuple[str, ...]] = ("mbt_gym", "external", "model-based")

    def __init__(
        self,
        *,
        mbtgym_env: str = "TradingEnvironment",
        mbtgym_module: str = "mbt_gym.gym",
        mbtgym_kwargs: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self.mbtgym_env_name = str(mbtgym_env)
        self.mbtgym_module = str(mbtgym_module)
        self.mbtgym_kwargs = dict(mbtgym_kwargs or {})
        self._inner: Any = None
        self._init_inner()

    def _init_inner(self) -> None:
        try:
            import importlib

            module = importlib.import_module(self.mbtgym_module)
            cls = getattr(module, self.mbtgym_env_name, None)
            if cls is None:
                raise ImportError(
                    f"{self.mbtgym_env_name!r} not found on {self.mbtgym_module!r}"
                )
            self._inner = cls(**self.mbtgym_kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "MbtGymAdapterEnv: failed to load %s.%s: %s",
                self.mbtgym_module, self.mbtgym_env_name, exc,
            )
            # Fallback to a 1-D dummy box so SB3 can still introspect
            # the spec without crashing in CI without mbt_gym.
            self._inner = None

    @property
    def action_space(self) -> Any:  # type: ignore[override]
        if self._inner is not None:
            return self._inner.action_space
        return gym.spaces.Box(low=-1.0, high=1.0, shape=(1,), dtype=np.float32)

    @property
    def observation_space(self) -> Any:  # type: ignore[override]
        if self._inner is not None:
            return self._inner.observation_space
        return gym.spaces.Box(low=-np.inf, high=np.inf, shape=(1,), dtype=np.float32)

    def reset(self, *, seed: int | None = None, options: dict | None = None):  # type: ignore[override]
        if self._inner is None:
            return np.zeros((1,), dtype=np.float32), {"mbtgym": False, "error": "mbt_gym not installed"}
        try:
            try:
                obs, info = self._inner.reset(seed=seed, options=options)
            except TypeError:
                obs = self._inner.reset()
                info = {}
        except Exception as exc:  # noqa: BLE001
            logger.warning("MbtGymAdapterEnv reset failed: %s", exc)
            obs, info = np.zeros((1,), dtype=np.float32), {"mbtgym": False, "error": str(exc)}
        info = {"mbtgym": True, **(info or {})}
        return obs, info

    def step(self, action):  # type: ignore[override]
        if self._inner is None:
            return (
                np.zeros((1,), dtype=np.float32),
                0.0,
                True,
                False,
                {"mbtgym": False},
            )
        try:
            result = self._inner.step(action)
        except Exception as exc:  # noqa: BLE001
            logger.warning("MbtGymAdapterEnv step failed: %s", exc)
            return (
                np.zeros((1,), dtype=np.float32),
                0.0,
                True,
                False,
                {"mbtgym": False, "error": str(exc)},
            )
        # Older Gym envs return 4-tuples; normalise to gymnasium 5-tuple.
        if len(result) == 5:
            obs, reward, terminated, truncated, info = result
        elif len(result) == 4:
            obs, reward, done, info = result
            terminated = bool(done)
            truncated = False
        else:
            raise RuntimeError(
                f"mbtgym env returned unexpected shape: {len(result)}-tuple"
            )
        info = {"mbtgym": True, **(info or {})}
        return obs, float(reward), bool(terminated), bool(truncated), info

    def _collect_env_state(self) -> dict[str, Any]:
        return {"inner": self.mbtgym_env_name, "mbtgym": self._inner is not None}


__all__ = ["MbtGymAdapterEnv"]
