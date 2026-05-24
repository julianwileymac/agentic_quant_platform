"""``TimeSeriesEncoder`` — abstract policy backbone (``rl_policy_backbone``).

Every concrete backbone subclasses :class:`TimeSeriesEncoder`. The
RL adapters (SB3, CleanRL, RLlib) bridge to it via the
:class:`BackboneFeaturesExtractor` in
:mod:`aqp_rl.policies.feature_extractors` — the adapter passes the
backbone alias + kwargs through the spec and the extractor
instantiates the backbone at policy-construction time.

Subclass contract
-----------------

A concrete backbone implements:

- :meth:`__init__` taking ``input_features``, ``sequence_length``,
  ``output_dim`` plus backbone-specific kwargs.
- :meth:`forward(x)` consuming a tensor of shape
  ``(batch_size, sequence_length, input_features)`` and returning a
  tensor of shape ``(batch_size, output_dim)``.

Observation reshaping
---------------------

Most AQP envs emit a flat ``(D,)`` observation. The
:class:`BackboneFeaturesExtractor` reshapes it into a sequence as
required by the backbone (the reshape rule defaults to the canonical
``(batch_size, sequence_length, input_features)`` where the
``sequence_length`` is the most recent ``L`` bars from the
:class:`LookbackStackBuilder`).
"""
from __future__ import annotations

import logging
from abc import abstractmethod
from typing import Any, ClassVar

import numpy as np

from aqp_rl.core.base import RL_KIND_POLICY_BACKBONE, RLComponent

logger = logging.getLogger(__name__)


class TimeSeriesEncoder(RLComponent):
    """Abstract backbone that maps a sequence into a fixed-dim feature vector.

    Concrete subclasses are torch.nn.Module-flavoured; we keep the
    base contract framework-agnostic so a researcher could in
    principle wire a JAX / TF backbone here without breaking the SB3
    extractor (the extractor degrades gracefully when ``forward``
    accepts numpy too).
    """

    __abstract_rl__: ClassVar[bool] = True
    rl_kind: ClassVar[str] = RL_KIND_POLICY_BACKBONE

    def __init__(
        self,
        *,
        input_features: int,
        sequence_length: int,
        output_dim: int,
        name: str | None = None,
    ) -> None:
        self.input_features = int(input_features)
        self.sequence_length = int(sequence_length)
        self.output_dim = int(output_dim)
        self.name = name or self.__class__.__name__

    @abstractmethod
    def forward(self, x: Any) -> Any:
        """Encode ``x`` into a ``(B, output_dim)`` feature tensor."""

    def __call__(self, x: Any) -> Any:
        return self.forward(x)

    def expected_input_shape(self) -> tuple[int, int]:
        return (self.sequence_length, self.input_features)

    def to_dict(self) -> dict[str, Any]:
        return {
            "class": type(self).__name__,
            "name": self.name,
            "input_features": self.input_features,
            "sequence_length": self.sequence_length,
            "output_dim": self.output_dim,
        }


def reshape_obs_to_sequence(
    obs: np.ndarray,
    *,
    sequence_length: int,
    input_features: int,
) -> np.ndarray:
    """Reshape flat ``(B, D)`` obs into ``(B, L, F)`` for a sequence backbone.

    Used by the :class:`BackboneFeaturesExtractor` when an env emits
    a flat observation that the backbone wants to consume as a
    sequence. The default reshape assumes the env's observation
    builder concatenated ``L * F`` features in chronological order
    (which is what :class:`LookbackStackBuilder` produces).

    Already-3D inputs of shape ``(B, L, F)`` are passed through
    unchanged. Already-3D inputs whose ``L`` or ``F`` don't match
    are raised as :class:`ValueError` because silently resizing a
    sequence dimension would corrupt the time axis.
    """
    arr = np.asarray(obs, dtype=np.float32)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    if arr.ndim == 3:
        if arr.shape[1:] != (sequence_length, input_features):
            raise ValueError(
                f"reshape_obs_to_sequence: 3D input with shape {tuple(arr.shape)} "
                f"does not match expected (-1, {sequence_length}, {input_features})"
            )
        return arr
    expected = sequence_length * input_features
    if arr.shape[-1] != expected:
        # If the flat obs is shorter than expected, pad with zeros
        # (zero-padded prefix so the most-recent bar is at the tail).
        # If longer, truncate to the tail.
        if arr.shape[-1] > expected:
            arr = arr[..., -expected:]
        else:
            pad = np.zeros((*arr.shape[:-1], expected - arr.shape[-1]), dtype=np.float32)
            arr = np.concatenate([pad, arr], axis=-1)
    return arr.reshape(arr.shape[0], sequence_length, input_features)


__all__ = [
    "TimeSeriesEncoder",
    "reshape_obs_to_sequence",
]
