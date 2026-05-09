"""Experiment contract — bundles env + agent + data + metrics into a unit run.

A :class:`BaseExperiment` mirrors :class:`aqp.ml.alpha_backtest_experiment`
for the RL world: one ``run(spec, runtime) -> result`` call drives
training, evaluation, MLflow logging, and Iceberg trajectory persistence.

Standard subclasses ship in :mod:`aqp.rl.experiments`:

- ``BasicRLExperiment`` — single train + holdout eval.
- ``WalkForwardRLExperiment`` — rolling windows.
- ``RewardAblationExperiment`` — sweep over reward-term weights.
- ``RLAlphaBacktestExperiment`` — train RL → backtest → register
  ``ml_alpha_backtest_runs`` row.
"""
from __future__ import annotations

from abc import abstractmethod
from typing import Any, ClassVar

from aqp.rl.core.base import RL_KIND_EXPERIMENT, RLComponent


class BaseExperiment(RLComponent):
    """Abstract experiment runner."""

    __abstract_rl__: ClassVar[bool] = True
    rl_kind: ClassVar[str] = RL_KIND_EXPERIMENT

    def __init__(self, *, name: str | None = None) -> None:
        self.name = name or self.__class__.__name__

    @abstractmethod
    def run(
        self,
        spec: Any,
        runtime: Any,
    ) -> dict[str, Any]:  # pragma: no cover - abstract
        """Execute the experiment and return a JSON-friendly result dict."""

    def to_dict(self) -> dict[str, Any]:
        return {"class": type(self).__name__, "name": self.name}


__all__ = ["BaseExperiment"]
