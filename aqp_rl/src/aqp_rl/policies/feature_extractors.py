"""SB3 / CleanRL bridge for :class:`TimeSeriesEncoder` backbones.

Concrete adapter strategy
-------------------------

Stable-Baselines3 expects a ``policy_kwargs={"features_extractor_class":
..., "features_extractor_kwargs": ...}`` payload where the class
inherits ``BaseFeaturesExtractor``. We expose
:class:`BackboneFeaturesExtractor` which:

1. Reads ``backbone_alias`` from kwargs.
2. Looks the alias up in the
   :data:`aqp.core.registry._kind_index['rl_policy_backbone']` map.
3. Instantiates the backbone with the inferred ``input_features``,
   ``sequence_length`` (from kwargs), and any backbone-specific
   ``backbone_kwargs``.
4. Forwards SB3's observation tensor through the backbone's
   ``forward``.

CleanRL adapter
---------------

The CleanRL PPO adapter calls :func:`build_backbone_from_alias`
directly to construct a feature trunk and stacks an MLP head /
value head on top.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

from aqp.core.registry import _kind_index
from aqp_rl.core.base import RL_KIND_POLICY_BACKBONE
from aqp_rl.policies.backbones.base import TimeSeriesEncoder

logger = logging.getLogger(__name__)


def build_backbone_from_alias(
    alias: str,
    *,
    input_features: int,
    sequence_length: int,
    output_dim: int = 128,
    backbone_kwargs: dict[str, Any] | None = None,
) -> TimeSeriesEncoder:
    """Construct a backbone by registry alias.

    The :class:`RLComponentMeta` metaclass auto-registers every
    backbone subclass under :data:`RL_KIND_POLICY_BACKBONE` so this
    function works without explicit imports of each backbone class.
    """
    registry = _kind_index.get(RL_KIND_POLICY_BACKBONE, {})
    cls = registry.get(alias)
    if cls is None:
        # Fall back to a case-insensitive lookup.
        lower = {k.lower(): v for k, v in registry.items()}
        cls = lower.get(alias.lower())
    if cls is None:
        raise KeyError(
            f"Unknown policy backbone alias {alias!r}. Registered: {sorted(registry)}"
        )
    kwargs = dict(backbone_kwargs or {})
    kwargs.setdefault("input_features", int(input_features))
    kwargs.setdefault("sequence_length", int(sequence_length))
    kwargs.setdefault("output_dim", int(output_dim))
    return cls(**kwargs)


# ---------------------------------------------------------------------------
# SB3 BaseFeaturesExtractor bridge.
# ---------------------------------------------------------------------------

try:
    import torch
    from torch import nn

    _TORCH_AVAILABLE = True
except Exception:
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    _TORCH_AVAILABLE = False


try:
    from stable_baselines3.common.torch_layers import BaseFeaturesExtractor

    _SB3_AVAILABLE = True
except Exception:
    BaseFeaturesExtractor = object  # type: ignore[assignment,misc]
    _SB3_AVAILABLE = False


class BackboneFeaturesExtractor(BaseFeaturesExtractor):  # type: ignore[misc]
    """SB3-compatible feature extractor wrapping a :class:`TimeSeriesEncoder`.

    Pass via ``policy_kwargs`` on any SB3 algorithm::

        agent_cfg = {
            "class": "SB3Adapter",
            "module_path": "aqp_rl.agents.sb3_adapter",
            "kwargs": {
                "algorithm": "PPO",
                "policy": "MlpPolicy",
                "policy_kwargs": {
                    "features_extractor_class": "aqp_rl.policies.feature_extractors.BackboneFeaturesExtractor",
                    "features_extractor_kwargs": {
                        "backbone_alias": "TransformerBackbone",
                        "sequence_length": 30,
                        "input_features": 32,
                        "features_dim": 128,
                        "backbone_kwargs": {"n_heads": 4, "n_layers": 2},
                    },
                },
            },
        }
    """

    def __init__(
        self,
        observation_space: Any,
        backbone_alias: str = "TransformerBackbone",
        *,
        sequence_length: int = 30,
        input_features: int | None = None,
        features_dim: int = 128,
        backbone_kwargs: dict[str, Any] | None = None,
    ) -> None:
        if not _SB3_AVAILABLE:
            raise ImportError("BackboneFeaturesExtractor requires stable_baselines3")
        if not _TORCH_AVAILABLE:
            raise ImportError("BackboneFeaturesExtractor requires torch")
        flat_dim = int(np.prod(observation_space.shape))
        if input_features is None:
            if flat_dim % sequence_length != 0:
                raise ValueError(
                    f"Cannot infer input_features: flat_dim={flat_dim} is not divisible by "
                    f"sequence_length={sequence_length}. Pass ``input_features`` explicitly."
                )
            input_features = flat_dim // sequence_length
        super().__init__(observation_space, features_dim=int(features_dim))
        self._backbone = build_backbone_from_alias(
            backbone_alias,
            input_features=input_features,
            sequence_length=sequence_length,
            output_dim=int(features_dim),
            backbone_kwargs=backbone_kwargs,
        )
        # SB3 expects the extractor to be an ``nn.Module`` so the
        # backbone parameters are added to the optimiser. Most of
        # our backbones store the parameters on ``self._module`` /
        # ``self._rnn`` / ``self._encoder`` / ``self._proj`` — we
        # register them all under one ``ParameterList`` so SB3 sees
        # them via the standard ``parameters()`` traversal.
        sub_modules = []
        for attr in ("_module", "_rnn", "_proj", "_encoder", "_patch_proj"):
            mod = getattr(self._backbone, attr, None)
            if isinstance(mod, nn.Module):
                sub_modules.append(mod)
        if sub_modules:
            self._registered_backbones = nn.ModuleList(sub_modules)

    def forward(self, observations: "torch.Tensor") -> "torch.Tensor":
        return self._backbone(observations)

    @property
    def backbone(self) -> TimeSeriesEncoder:
        return self._backbone


__all__ = [
    "BackboneFeaturesExtractor",
    "build_backbone_from_alias",
]
