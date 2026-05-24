"""Observation builder contract.

Each observation builder reports its ``output_shape`` and ``feature_names``
up-front so the UI builders can validate composition before training and
the API ``/rl/lab/preview-observation`` route can render the resulting
vector for a single step.

The default :class:`StackedObservationBuilder` concatenates several
sub-builders along the last axis (cash / weights / technical / risk
columns), which mirrors FinRL's ``state = [cash, prices, holdings,
indicators, vix/turbulence]`` layout but lets researchers compose new
state shapes from registry-driven building blocks.
"""
from __future__ import annotations

from abc import abstractmethod
from typing import Any, ClassVar, Mapping

import numpy as np

from aqp_rl.core.base import RL_KIND_OBSERVATION, RLComponent


class BaseObservationBuilder(RLComponent):
    """Abstract observation builder.

    Subclasses must implement :meth:`build` and either expose an
    explicit ``feature_names`` list or override :meth:`feature_names`.
    The runtime concatenates outputs of several builders by calling
    :meth:`build(idx, env_state) -> np.ndarray` and stacking the
    resulting 1-D vectors.
    """

    __abstract_rl__: ClassVar[bool] = True
    rl_kind: ClassVar[str] = RL_KIND_OBSERVATION

    def __init__(self, *, name: str | None = None) -> None:
        self.name = name or self.__class__.__name__

    @abstractmethod
    def build(
        self, idx: int, env_state: Mapping[str, Any]
    ) -> np.ndarray:  # pragma: no cover - abstract
        """Return a 1-D ``np.float32`` vector for step ``idx``."""

    def reset(self, env_state: Mapping[str, Any]) -> None:
        """Hook for stateful builders (rolling moments, EWMA…)."""

    @property
    def output_shape(self) -> tuple[int, ...]:
        """Return the shape of :meth:`build`'s output. Default is ``(-1,)``.

        Subclasses with a known fixed length should override.
        """
        return (-1,)

    def feature_names(self) -> list[str]:
        """Return human-readable column names for each output dim."""
        n = self.output_shape[0]
        if n < 0:
            return []
        return [f"{self.name}_{i}" for i in range(n)]

    def to_dict(self) -> dict[str, Any]:
        return {
            "class": type(self).__name__,
            "name": self.name,
            "output_shape": list(self.output_shape),
            "feature_names": self.feature_names(),
        }


class StackedObservationBuilder(BaseObservationBuilder):
    """Concatenate the outputs of several builders along axis 0.

    YAML composition example::

        observation:
          class: StackedObservationBuilder
          module_path: aqp_rl.core.observation
          kwargs:
            builders:
              - class: TechnicalIndicatorBuilder
                kwargs: { indicators: [macd, rsi_14, sma_20] }
              - class: TurbulenceBuilder
                kwargs: { lookback: 252 }
    """

    rl_alias: ClassVar[str] = "StackedObservationBuilder"
    rl_source: ClassVar[str] = "aqp"
    rl_tags: ClassVar[tuple[str, ...]] = ("composite",)

    def __init__(
        self,
        builders: list[BaseObservationBuilder | dict[str, Any]] | None = None,
        *,
        name: str | None = None,
    ) -> None:
        super().__init__(name=name)
        from aqp.core.registry import build_from_config

        resolved: list[BaseObservationBuilder] = []
        for b in builders or []:
            if isinstance(b, BaseObservationBuilder):
                resolved.append(b)
            elif isinstance(b, dict) and "class" in b:
                obj = build_from_config(b)
                if not isinstance(obj, BaseObservationBuilder):
                    raise TypeError(
                        f"StackedObservationBuilder expects BaseObservationBuilder, got {type(obj)}"
                    )
                resolved.append(obj)
            else:
                raise TypeError(f"Unsupported builder spec: {type(b).__name__}")
        self.builders = resolved

    def reset(self, env_state: Mapping[str, Any]) -> None:
        for b in self.builders:
            b.reset(env_state)

    def build(self, idx: int, env_state: Mapping[str, Any]) -> np.ndarray:
        if not self.builders:
            return np.zeros(0, dtype=np.float32)
        parts = [np.asarray(b.build(idx, env_state), dtype=np.float32).ravel() for b in self.builders]
        out = np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
        out = np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)
        return out.astype(np.float32, copy=False)

    @property
    def output_shape(self) -> tuple[int, ...]:
        total = 0
        for b in self.builders:
            n = b.output_shape[0]
            if n < 0:
                return (-1,)
            total += int(n)
        return (total,)

    def feature_names(self) -> list[str]:
        names: list[str] = []
        for b in self.builders:
            names.extend(b.feature_names() or [])
        return names

    def to_dict(self) -> dict[str, Any]:
        return {
            "class": "StackedObservationBuilder",
            "module_path": "aqp_rl.core.observation",
            "kwargs": {"builders": [b.to_dict() for b in self.builders]},
        }


__all__ = [
    "BaseObservationBuilder",
    "StackedObservationBuilder",
]
