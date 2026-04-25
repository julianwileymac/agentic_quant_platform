"""Tier B PyTorch model stubs.

These classes register cleanly so the Strategy Browser, registry
introspection, and YAML loaders can enumerate them, but they raise
``NotImplementedError`` on ``fit``. Each stub carries a reference pointer
to the canonical qlib implementation so downstream implementers know where
to port from.

Reference paths (all under ``inspiration/qlib-main/qlib/contrib/model/``):

- ``pytorch_gats.py`` / ``pytorch_gats_ts.py`` — ``GATsModel``
- ``pytorch_hist.py``                          — ``HISTModel``
- ``pytorch_tra.py``                           — ``TRAModel``
- ``pytorch_add.py``                           — ``ADDModel``
- ``pytorch_adarnn.py``                        — ``ADARNNModel``
- ``pytorch_tcts.py``                          — ``TCTSModel``
- ``pytorch_sfm.py``                           — ``SFMModel``
- ``pytorch_sandwich.py``                      — ``SandwichModel``
- ``pytorch_krnn.py``                          — ``KRNNModel``
- ``pytorch_igmtf.py``                         — ``IGMTFModel``
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from aqp.core.registry import register
from aqp.ml.base import Model


class _TierBStub(Model):
    """Base stub — subclasses set ``reference_path`` and ``description``."""

    reference_path: str = ""
    description: str = ""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    def fit(self, dataset: Any, reweighter: Any | None = None) -> Model:  # pragma: no cover
        raise NotImplementedError(
            f"{type(self).__name__} is a scaffolded Tier B model. "
            f"See: {self.reference_path}"
        )

    def predict(self, dataset: Any, segment: str | slice = "test") -> pd.Series:  # pragma: no cover
        raise NotImplementedError(
            f"{type(self).__name__}.predict is not yet implemented. "
            f"See: {self.reference_path}"
        )


@register("GATsModel")
class GATsModel(_TierBStub):
    reference_path = "inspiration/qlib-main/qlib/contrib/model/pytorch_gats.py"
    description = "Graph Attention Networks on symbol relation graph."


@register("HISTModel")
class HISTModel(_TierBStub):
    reference_path = "inspiration/qlib-main/qlib/contrib/model/pytorch_hist.py"
    description = "Hierarchical + concept embeddings (pre-trained)."


@register("TRAModel")
class TRAModel(_TierBStub):
    reference_path = "inspiration/qlib-main/qlib/contrib/model/pytorch_tra.py"
    description = "Temporal Routing Adapter over RNN / Transformer backbone."


@register("ADDModel")
class ADDModel(_TierBStub):
    reference_path = "inspiration/qlib-main/qlib/contrib/model/pytorch_add.py"
    description = "Adversarial Domain Adaptation + forecast head (RevGrad)."


@register("ADARNNModel")
class ADARNNModel(_TierBStub):
    reference_path = "inspiration/qlib-main/qlib/contrib/model/pytorch_adarnn.py"
    description = "Adaptive RNN for temporal domain adaptation."


@register("TCTSModel")
class TCTSModel(_TierBStub):
    reference_path = "inspiration/qlib-main/qlib/contrib/model/pytorch_tcts.py"
    description = "Decoupled forecaster + temporal scheduler."


@register("SFMModel")
class SFMModel(_TierBStub):
    reference_path = "inspiration/qlib-main/qlib/contrib/model/pytorch_sfm.py"
    description = "State Frequency Memory — LSTM with frequency mixing."


@register("SandwichModel")
class SandwichModel(_TierBStub):
    reference_path = "inspiration/qlib-main/qlib/contrib/model/pytorch_sandwich.py"
    description = "CNN + KRNN 'sandwich' stack."


@register("KRNNModel")
class KRNNModel(_TierBStub):
    reference_path = "inspiration/qlib-main/qlib/contrib/model/pytorch_krnn.py"
    description = "CNN + RNN hybrid encoder."


@register("IGMTFModel")
class IGMTFModel(_TierBStub):
    reference_path = "inspiration/qlib-main/qlib/contrib/model/pytorch_igmtf.py"
    description = "Interpretable graph multi-task fusion (LSTM + GRU)."


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
