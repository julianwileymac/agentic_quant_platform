"""PyTorch port of stock-analysis-engine's Keras MLP regressor.

Source: ``inspiration/stock-analysis-engine-master/analysis_engine/ai/build_regression_dnn.py``

Original was Keras 2 with ``tensorflow.keras.wrappers.scikit_learn.KerasRegressor``.
Ported to PyTorch keeping the layer-count and dropout topology
(8→6→1 with intermediate ReLU + dropout). MinMaxScaler on inputs.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from aqp.core.registry import register
from aqp.ml.models.spm._torch_base import TorchForecasterBase, TrainConfig

logger = logging.getLogger(__name__)


@register("KerasMLPRegressor", source="sae", category="mlp", kind="model")
class KerasMLPRegressor(TorchForecasterBase):
    """Two-hidden-layer MLP (8 → 6 → 1) with optional input scaling.

    Despite the name, this is a PyTorch implementation; the name is kept
    for source traceability.
    """

    def __init__(
        self,
        hidden_sizes: tuple[int, ...] = (8, 6),
        dropout: float = 0.0,
        use_minmax: bool = True,
        config: TrainConfig | None = None,
        **overrides: Any,
    ) -> None:
        super().__init__(config=config, **overrides)
        self.hidden_sizes = hidden_sizes
        self.dropout = dropout
        self.use_minmax = use_minmax
        self._scaler = None

    def build_module(self):
        import torch  # noqa: F401
        from torch import nn
        cfg = self.config

        class _MLP(nn.Module):
            def __init__(self, n_features, hidden_sizes, dropout):
                super().__init__()
                layers: list[nn.Module] = []
                in_dim = n_features
                for h in hidden_sizes:
                    layers.extend([nn.Linear(in_dim, h), nn.ReLU(), nn.Dropout(dropout)])
                    in_dim = h
                layers.append(nn.Linear(in_dim, 1))
                self.net = nn.Sequential(*layers)

            def forward(self, x):
                # MLP wants (B, F) — collapse seq dim by taking last step
                if x.dim() == 3:
                    x = x[:, -1, :]
                return self.net(x)

        return _MLP(cfg.n_features, self.hidden_sizes, self.dropout)

    def _extract_xy(self, dataset):
        X, y = super()._extract_xy(dataset)
        if self.use_minmax and len(X) > 0:
            try:
                from sklearn.preprocessing import MinMaxScaler
            except ImportError:
                logger.warning("sklearn not installed; skipping MinMax scaling")
                return X, y
            n_features = X.shape[2]
            flat = X.reshape(-1, n_features)
            if self._scaler is None:
                self._scaler = MinMaxScaler()
                flat = self._scaler.fit_transform(flat)
            else:
                flat = self._scaler.transform(flat)
            X = flat.reshape(X.shape).astype(np.float32)
        return X, y


__all__ = ["KerasMLPRegressor"]
