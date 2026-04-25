"""Shared PyTorch model helpers.

All Tier A Torch models inherit from :class:`BaseTorchModel` which implements
the :class:`aqp.ml.base.ModelFT` contract on top of a user-provided
``build_module()``.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from aqp.ml.base import ModelFT, Reweighter
from aqp.ml.dataset import TSDataSampler
from aqp.ml.models._utils import predict_to_series, prepare_panel, split_xy

logger = logging.getLogger(__name__)


def _import_torch():
    try:
        import torch
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "torch is not installed. Install with `pip install -e \".[ml-torch]\"`"
        ) from e
    return torch


class BaseTorchModel(ModelFT):
    """Shared training loop for dense / sequence PyTorch models.

    Subclasses implement ``build_module(input_size: int) -> nn.Module`` and,
    if sequence-based, override ``is_sequence = True``.
    """

    is_sequence: bool = False
    step_len: int = 20

    def __init__(
        self,
        lr: float = 1e-3,
        batch_size: int = 256,
        n_epochs: int = 20,
        weight_decay: float = 1e-5,
        device: str = "auto",
        early_stop: int = 5,
        seed: int = 42,
    ) -> None:
        self.lr = float(lr)
        self.batch_size = int(batch_size)
        self.n_epochs = int(n_epochs)
        self.weight_decay = float(weight_decay)
        self.device = device
        self.early_stop = int(early_stop)
        self.seed = int(seed)
        self.module: Any | None = None
        self._input_size: int | None = None

    # ---- required overrides ------------------------------------------

    def build_module(self, input_size: int) -> Any:
        raise NotImplementedError

    # ---- Model API ---------------------------------------------------

    def fit(self, dataset: Any, reweighter: Reweighter | None = None) -> BaseTorchModel:
        torch = _import_torch()
        device = self._device(torch)
        torch.manual_seed(self.seed)

        if self.is_sequence:
            X_train, y_train = _sequence_tensors(dataset, "train", self.step_len, torch)
            try:
                X_val, y_val = _sequence_tensors(dataset, "valid", self.step_len, torch)
            except Exception:
                X_val = y_val = None
            input_size = X_train.shape[-1]
        else:
            panel = prepare_panel(dataset, "train")
            X, y, _ = split_xy(panel)
            X_train = torch.tensor(X, dtype=torch.float32)
            y_train = torch.tensor(y, dtype=torch.float32)
            try:
                val_panel = prepare_panel(dataset, "valid")
                Xv, yv, _ = split_xy(val_panel)
                X_val = torch.tensor(Xv, dtype=torch.float32)
                y_val = torch.tensor(yv, dtype=torch.float32)
            except Exception:
                X_val = y_val = None
            input_size = X.shape[-1]

        self._input_size = int(input_size)
        self.module = self.build_module(self._input_size).to(device)
        opt = torch.optim.Adam(self.module.parameters(), lr=self.lr, weight_decay=self.weight_decay)
        loss_fn = torch.nn.MSELoss()

        n = X_train.shape[0]
        best_val = float("inf")
        patience = 0
        for epoch in range(self.n_epochs):
            self.module.train()
            perm = torch.randperm(n)
            train_loss = 0.0
            for i in range(0, n, self.batch_size):
                idx = perm[i : i + self.batch_size]
                xb = X_train[idx].to(device)
                yb = y_train[idx].to(device)
                opt.zero_grad()
                out = self.module(xb)
                if out.ndim > 1:
                    out = out.squeeze(-1)
                loss = loss_fn(out, yb)
                loss.backward()
                opt.step()
                train_loss += float(loss.item()) * xb.shape[0]
            train_loss /= max(n, 1)

            if X_val is not None and y_val is not None:
                self.module.eval()
                with torch.no_grad():
                    out = self.module(X_val.to(device))
                    if out.ndim > 1:
                        out = out.squeeze(-1)
                    val = float(loss_fn(out, y_val.to(device)).item())
                if val < best_val - 1e-6:
                    best_val = val
                    patience = 0
                else:
                    patience += 1
                if patience >= self.early_stop:
                    logger.info(
                        "early stop at epoch %d (train=%.5f val=%.5f)", epoch, train_loss, val
                    )
                    break
        return self

    def finetune(self, dataset: Any) -> BaseTorchModel:
        # Reuse fit() with a smaller epoch count; callers are expected to
        # set ``n_epochs`` before calling if they want a different budget.
        return self.fit(dataset)

    def predict(self, dataset: Any, segment: str | slice = "test") -> pd.Series:
        torch = _import_torch()
        if self.module is None:
            raise RuntimeError(f"{type(self).__name__}.predict called before fit().")
        device = self._device(torch)
        seg = segment if isinstance(segment, str) else "test"

        if self.is_sequence:
            X, _ = _sequence_tensors(dataset, seg, self.step_len, torch)
        else:
            panel = prepare_panel(dataset, seg)
            X, _, _ = split_xy(panel)
            X = torch.tensor(X, dtype=torch.float32)

        self.module.eval()
        preds: list[np.ndarray] = []
        with torch.no_grad():
            for i in range(0, X.shape[0], self.batch_size):
                xb = X[i : i + self.batch_size].to(device)
                out = self.module(xb)
                if out.ndim > 1:
                    out = out.squeeze(-1)
                preds.append(out.cpu().numpy())
        arr = np.concatenate(preds) if preds else np.zeros(0, dtype=float)
        return predict_to_series(dataset, seg, arr)

    # ---- internals ---------------------------------------------------

    def _device(self, torch: Any):
        if self.device == "auto":
            return torch.device("cuda" if torch.cuda.is_available() else "cpu")
        return torch.device(self.device)


def _sequence_tensors(
    dataset: Any,
    segment: str,
    step_len: int,
    torch: Any,
) -> tuple[Any, Any]:
    """Build (batch, step_len, feature) tensors from a ``TSDatasetH`` segment."""
    sampler = getattr(dataset, "prepare", None)
    if sampler is None:
        raise TypeError("dataset is not a TSDatasetH / DatasetH")
    try:
        prepared = dataset.prepare(segment, col_set="__all__")
    except TypeError:
        prepared = dataset.prepare(segment)
    if isinstance(prepared, TSDataSampler):
        sampler_obj = prepared
    else:
        # DatasetH returned a plain frame — fall back to a sliding window.
        sampler_obj = TSDataSampler(prepared, step_len=step_len)

    xs: list[np.ndarray] = []
    ys: list[float] = []
    for i in range(len(sampler_obj)):
        x, y = sampler_obj[i]
        xs.append(x)
        ys.append(y)
    X = np.stack(xs) if xs else np.zeros((0, step_len, 1), dtype=np.float32)
    Y = np.asarray(ys, dtype=np.float32)
    return (
        torch.tensor(X, dtype=torch.float32),
        torch.tensor(Y, dtype=torch.float32),
    )


__all__ = ["BaseTorchModel"]
