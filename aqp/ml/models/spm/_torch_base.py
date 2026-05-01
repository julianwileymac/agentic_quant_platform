"""PyTorch base for SPM-style forecasters.

Provides ``TorchForecasterBase`` — a thin ``Model`` subclass with a
small training loop, MSE loss, and a sequence-windowed featurizer.
SPM ports inherit and override :meth:`build` to define the network.

PyTorch is imported lazily so the rest of the platform doesn't pull
torch unless a TorchForecasterBase descendant is actually constructed.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from aqp.ml.base import Model, Reweighter

logger = logging.getLogger(__name__)


def _ensure_torch():
    try:
        import torch  # noqa: F401
        from torch import nn  # noqa: F401
        return True
    except ImportError as exc:  # pragma: no cover
        raise ImportError("PyTorch is required for SPM forecasters; pip install torch") from exc


@dataclass
class TrainConfig:
    seq_len: int = 20
    hidden_size: int = 64
    num_layers: int = 1
    dropout: float = 0.0
    lr: float = 1e-3
    epochs: int = 5
    batch_size: int = 32
    n_features: int = 1
    device: str = "cpu"


def _windowize(arr: np.ndarray, seq_len: int) -> tuple[np.ndarray, np.ndarray]:
    """Slide ``seq_len`` windows over a 1-D or 2-D array.

    Returns ``(X, y)`` where ``X`` has shape ``(n - seq_len, seq_len, n_features)``
    and ``y`` has shape ``(n - seq_len,)`` taken from the last column of ``arr``
    if 2-D, else the array itself if 1-D.
    """
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    n = arr.shape[0]
    if n <= seq_len:
        return np.empty((0, seq_len, arr.shape[1])), np.empty(0)
    X = np.stack([arr[i : i + seq_len] for i in range(n - seq_len)], axis=0)
    y = arr[seq_len:, 0]  # forecast first column (typically close)
    return X.astype(np.float32), y.astype(np.float32)


class TorchForecasterBase(Model):
    """Reusable training loop for SPM ports.

    Subclasses override :meth:`build_module` to populate ``self.module``
    (a ``torch.nn.Module``). The forward pass should accept a tensor of
    shape ``(batch, seq_len, n_features)`` and emit one scalar per row.
    """

    def __init__(self, config: TrainConfig | None = None, **overrides: Any) -> None:
        self.config: TrainConfig = config or TrainConfig()
        for k, v in overrides.items():
            if hasattr(self.config, k):
                setattr(self.config, k, v)
        self.module: Any = None
        self._fitted: bool = False

    # ------------------------------------------------------------------
    # Subclasses must override
    # ------------------------------------------------------------------

    def build_module(self):
        """Return a ``torch.nn.Module`` instance configured from ``self.config``."""
        raise NotImplementedError("Subclasses must implement build_module()")

    # ------------------------------------------------------------------
    # Standard Model contract
    # ------------------------------------------------------------------

    def fit(self, dataset: Any, reweighter: Reweighter | None = None) -> "TorchForecasterBase":
        _ensure_torch()
        import torch
        from torch import nn

        X, y = self._extract_xy(dataset)
        if len(X) == 0:
            logger.warning("Empty training set; skipping fit")
            return self

        self.config.n_features = int(X.shape[2])
        self.module = self.build_module()
        device = torch.device(self.config.device)
        self.module.to(device)
        loss_fn = nn.MSELoss()
        opt = torch.optim.Adam(self.module.parameters(), lr=self.config.lr)

        X_t = torch.from_numpy(X).to(device)
        y_t = torch.from_numpy(y).to(device)

        n = X.shape[0]
        for epoch in range(self.config.epochs):
            self.module.train()
            perm = torch.randperm(n, device=device)
            losses = []
            for i in range(0, n, self.config.batch_size):
                idx = perm[i : i + self.config.batch_size]
                xb = X_t[idx]
                yb = y_t[idx]
                opt.zero_grad()
                pred = self.module(xb).squeeze(-1)
                loss = loss_fn(pred, yb)
                loss.backward()
                opt.step()
                losses.append(float(loss.item()))
            if losses:
                logger.debug("epoch %d/%d loss=%.6f", epoch + 1, self.config.epochs, float(np.mean(losses)))
        self._fitted = True
        return self

    def predict(self, dataset: Any, segment: str | slice = "test") -> pd.Series:
        if not self._fitted or self.module is None:
            raise RuntimeError("Model is not fitted; call fit() first.")
        _ensure_torch()
        import torch

        X, _ = self._extract_xy(dataset)
        if len(X) == 0:
            return pd.Series(dtype=float)
        device = torch.device(self.config.device)
        self.module.eval()
        with torch.no_grad():
            preds = self.module(torch.from_numpy(X).to(device)).squeeze(-1).cpu().numpy()
        index = self._extract_index(dataset)
        if index is None or len(index) != len(preds):
            return pd.Series(preds)
        return pd.Series(preds, index=index[-len(preds):])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_xy(self, dataset: Any) -> tuple[np.ndarray, np.ndarray]:
        """Pull ``(X, y)`` out of any of the supported dataset shapes."""
        if hasattr(dataset, "to_arrays"):
            features, labels = dataset.to_arrays()
            arr = np.column_stack([labels, features]) if features.ndim == 2 else labels
            return _windowize(arr, self.config.seq_len)
        if hasattr(dataset, "features") and hasattr(dataset, "labels"):
            features = dataset.features().to_numpy(dtype=float)
            labels = dataset.labels().to_numpy(dtype=float)
            arr = np.column_stack([labels, features]) if features.ndim == 2 else labels
            return _windowize(arr, self.config.seq_len)
        if isinstance(dataset, pd.DataFrame):
            arr = dataset.to_numpy(dtype=float)
            return _windowize(arr, self.config.seq_len)
        if isinstance(dataset, pd.Series):
            return _windowize(dataset.to_numpy(dtype=float), self.config.seq_len)
        if isinstance(dataset, np.ndarray):
            return _windowize(dataset, self.config.seq_len)
        if isinstance(dataset, tuple) and len(dataset) == 2:
            features, labels = dataset
            arr = np.column_stack([labels, features]) if features.ndim == 2 else labels
            return _windowize(arr, self.config.seq_len)
        raise TypeError(f"Unsupported dataset type for TorchForecasterBase: {type(dataset)!r}")

    @staticmethod
    def _extract_index(dataset: Any) -> pd.Index | None:
        if hasattr(dataset, "index"):
            return getattr(dataset, "index")
        if isinstance(dataset, pd.DataFrame | pd.Series):
            return dataset.index
        return None


__all__ = ["TorchForecasterBase", "TrainConfig"]
