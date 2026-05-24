"""Ensembler contract — orchestrate multiple training runs / agents.

Walk-forward, best-of-N, curriculum, and meta-ensemble strategies all
inherit from :class:`BaseEnsembler`. The runtime treats an ensembler as
a meta-agent: ``train(spec)`` runs the inner training loops and
``select(env)`` returns the best member for inference.
"""
from __future__ import annotations

from abc import abstractmethod
from typing import Any, ClassVar

from aqp_rl.core.base import RL_KIND_ENSEMBLER, RLComponent


class BaseEnsembler(RLComponent):
    """Abstract ensemble orchestrator."""

    __abstract_rl__: ClassVar[bool] = True
    rl_kind: ClassVar[str] = RL_KIND_ENSEMBLER

    def __init__(self, *, name: str | None = None) -> None:
        self.name = name or self.__class__.__name__
        self.results: list[dict[str, Any]] = []

    @abstractmethod
    def train(self, spec: Any, runtime: Any) -> dict[str, Any]:  # pragma: no cover - abstract
        """Run the ensemble training loop. Returns a summary dict."""

    def predict(self, obs: Any, deterministic: bool = True) -> Any:
        """Default prediction: defer to the best member if one is set."""
        best = getattr(self, "_best", None)
        if best is None:
            raise RuntimeError("Ensembler has no best member yet — call train() first.")
        return best.predict(obs, deterministic=deterministic)

    def to_dict(self) -> dict[str, Any]:
        return {"class": type(self).__name__, "name": self.name}


__all__ = ["BaseEnsembler"]
