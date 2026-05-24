"""``RegimeAwareObservation`` — append regime one-hot to existing obs.

The :class:`SliceAndMergeRegimeFlow` analysis flow (Phase 6 of the
production-enhancement plan) writes per-bar regime labels into the
gold-tier Iceberg table ``aqp_gold_analysis_market_dynamics_modeling``.
This observation builder reads the precomputed labels (either passed
in as a dict / DataFrame or sourced from ``env_state['regime_labels']``
when the env stamps them) and appends a one-hot vector of length
``n_regimes`` to the rest of the observation.

Two integration paths
=====================

1. **Inline**: the env stamps ``env_state['regime_label']`` (a single
   integer) every step. The builder produces a one-hot from that
   scalar.
2. **Precomputed**: pass ``labels=[…]`` at construction time (e.g.
   the entire ticker's regime label series loaded once from the
   gold table). The builder indexes by ``idx``.

The default fallback emits a zero vector when no label is available
so the observation builder composes cleanly with synthetic envs that
don't have an MDM run yet.

Hard rule 19: registered through the :class:`RLComponent` metaclass.
"""
from __future__ import annotations

from typing import Any, ClassVar, Mapping, Sequence

import numpy as np

from aqp_rl.core.observation import BaseObservationBuilder


class RegimeAwareObservation(BaseObservationBuilder):
    """One-hot regime-label observation appendage.

    Parameters
    ----------
    n_regimes:
        Number of regimes the MDM run produced. Output is a length-
        ``n_regimes`` one-hot.
    labels:
        Optional precomputed per-bar regime label sequence. When set,
        :meth:`build` indexes into this with ``idx``. When ``None``,
        :meth:`build` reads ``env_state['regime_label']`` instead.
    label_key:
        ``env_state`` key holding the current regime label when
        ``labels`` is not pre-set. Default ``'regime_label'``.
    """

    rl_alias: ClassVar[str] = "regime_aware"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "regime"
    rl_tags: ClassVar[tuple[str, ...]] = ("regime", "market_dynamics", "one_hot")

    def __init__(
        self,
        *,
        n_regimes: int,
        labels: Sequence[int] | None = None,
        label_key: str = "regime_label",
        name: str | None = None,
    ) -> None:
        if n_regimes < 1:
            raise ValueError(f"RegimeAwareObservation needs n_regimes ≥ 1; got {n_regimes!r}")
        super().__init__(name=name)
        self.n_regimes = int(n_regimes)
        self.labels: np.ndarray | None = (
            np.asarray(labels, dtype=np.int64) if labels is not None else None
        )
        self.label_key = str(label_key)

    def reset(self, env_state: Mapping[str, Any]) -> None:
        """No-op — regime labels are precomputed or stamped per step."""

    def build(self, idx: int, env_state: Mapping[str, Any]) -> np.ndarray:
        label: int | None = None
        if self.labels is not None:
            if 0 <= idx < len(self.labels):
                label = int(self.labels[idx])
        elif env_state and self.label_key in env_state:
            try:
                label = int(env_state[self.label_key])
            except (TypeError, ValueError):
                label = None
        one_hot = np.zeros(self.n_regimes, dtype=np.float32)
        if label is not None and 0 <= label < self.n_regimes:
            one_hot[label] = 1.0
        return one_hot

    @property
    def output_shape(self) -> tuple[int, ...]:
        return (self.n_regimes,)

    def feature_names(self) -> list[str]:
        return [f"regime_{i}" for i in range(self.n_regimes)]

    def to_dict(self) -> dict[str, Any]:
        out = super().to_dict()
        out["n_regimes"] = self.n_regimes
        out["label_key"] = self.label_key
        out["has_precomputed_labels"] = self.labels is not None
        return out


__all__ = ["RegimeAwareObservation"]
