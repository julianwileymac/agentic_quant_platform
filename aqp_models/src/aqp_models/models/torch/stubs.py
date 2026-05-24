"""Backward-compatible re-exports for the Tier-B PyTorch model classes.

These models used to live in this module as no-op stubs; they now have
real implementations under per-model files. Imports remain valid so
existing YAML configs and code keep working.
"""
from __future__ import annotations

from aqp_models.models.torch.adarnn import ADARNNModel
from aqp_models.models.torch.add import ADDModel
from aqp_models.models.torch.gats import GATsModel
from aqp_models.models.torch.hist import HISTModel
from aqp_models.models.torch.igmtf import IGMTFModel
from aqp_models.models.torch.krnn import KRNNModel
from aqp_models.models.torch.sandwich import SandwichModel
from aqp_models.models.torch.sfm import SFMModel
from aqp_models.models.torch.tcts import TCTSModel
from aqp_models.models.torch.tra import TRAModel

__all__ = [
    "ADARNNModel",
    "ADDModel",
    "GATsModel",
    "HISTModel",
    "IGMTFModel",
    "KRNNModel",
    "SFMModel",
    "SandwichModel",
    "TCTSModel",
    "TRAModel",
]
