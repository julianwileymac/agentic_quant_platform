"""Policy backbones — registered :class:`TimeSeriesEncoder` subclasses."""
from __future__ import annotations

from aqp_rl.policies.backbones.autoencoder import AutoencoderBackbone
from aqp_rl.policies.backbones.base import TimeSeriesEncoder
from aqp_rl.policies.backbones.dual_head import DualHeadContinuousBackbone
from aqp_rl.policies.backbones.eiie_conv import EIIEConvBackbone
from aqp_rl.policies.backbones.hft_q import HFTQBackbone
from aqp_rl.policies.backbones.market_scorer import MarketScorerBackbone
from aqp_rl.policies.backbones.patchtst import PatchTSTBackbone
from aqp_rl.policies.backbones.pd_dual_rnn import PDDualRNNBackbone
from aqp_rl.policies.backbones.recurrent import RecurrentBackbone
from aqp_rl.policies.backbones.sagcn import SAGCNBackbone
from aqp_rl.policies.backbones.sarl_classifier import SARLClassifierBackbone
from aqp_rl.policies.backbones.transformer import TransformerBackbone

__all__ = [
    "AutoencoderBackbone",
    "DualHeadContinuousBackbone",
    "EIIEConvBackbone",
    "HFTQBackbone",
    "MarketScorerBackbone",
    "PDDualRNNBackbone",
    "PatchTSTBackbone",
    "RecurrentBackbone",
    "SAGCNBackbone",
    "SARLClassifierBackbone",
    "TimeSeriesEncoder",
    "TransformerBackbone",
]
