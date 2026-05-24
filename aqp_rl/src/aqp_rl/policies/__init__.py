"""RL policy backbones — Transformer / RNN / Autoencoder / PatchTST.

Each backbone is a registered :class:`TimeSeriesEncoder` subclass
(``rl_kind='rl_policy_backbone'``). The :class:`BackboneFeaturesExtractor`
bridges them onto Stable-Baselines3's ``BaseFeaturesExtractor``
contract so any SB3 algorithm (PPO, SAC, TD3, …) can use them as the
policy's feature trunk.

Spec wiring
-----------

``RLExperimentSpec.agent.kwargs.policy_kwargs.features_extractor_class =
"aqp_rl.policies.feature_extractors.BackboneFeaturesExtractor"`` plus
``features_extractor_kwargs = {"backbone_alias": "TransformerBackbone",
"sequence_length": 30, "features_dim": 128, "backbone_kwargs": {...}}``
selects the backbone by alias and configures it.

The CleanRL adapter ships a parallel
:class:`aqp_rl.agents.cleanrl_adapter.CleanRLAdapter` that calls
:func:`aqp_rl.policies.build_backbone_from_alias` directly when
``policy_backbone`` is set on the adapter spec.
"""
from __future__ import annotations

from aqp_rl.policies.backbones.autoencoder import AutoencoderBackbone
from aqp_rl.policies.backbones.base import TimeSeriesEncoder
from aqp_rl.policies.backbones.patchtst import PatchTSTBackbone
from aqp_rl.policies.backbones.recurrent import RecurrentBackbone
from aqp_rl.policies.backbones.transformer import TransformerBackbone
from aqp_rl.policies.feature_extractors import (
    BackboneFeaturesExtractor,
    build_backbone_from_alias,
)

__all__ = [
    "AutoencoderBackbone",
    "BackboneFeaturesExtractor",
    "PatchTSTBackbone",
    "RecurrentBackbone",
    "TimeSeriesEncoder",
    "TransformerBackbone",
    "build_backbone_from_alias",
]
