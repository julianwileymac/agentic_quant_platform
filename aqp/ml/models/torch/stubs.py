"""Backward-compatible re-exports for the Tier-B PyTorch model classes.

These models used to live in this module as no-op stubs; they now have
real implementations under per-model files. Imports remain valid so
existing YAML configs and code keep working.
"""
from __future__ import annotations

from aqp.ml.models.torch.adarnn import ADARNNModel
from aqp.ml.models.torch.add import ADDModel
from aqp.ml.models.torch.gats import GATsModel
from aqp.ml.models.torch.hist import HISTModel
from aqp.ml.models.torch.igmtf import IGMTFModel
from aqp.ml.models.torch.krnn import KRNNModel
from aqp.ml.models.torch.sandwich import SandwichModel
from aqp.ml.models.torch.sfm import SFMModel
from aqp.ml.models.torch.tcts import TCTSModel
from aqp.ml.models.torch.tra import TRAModel

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
