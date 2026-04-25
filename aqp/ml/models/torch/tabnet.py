"""TabNet — wraps ``pytorch-tabnet`` for tabular features."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from aqp.core.registry import register
from aqp.ml.base import ModelFT, Reweighter
from aqp.ml.models._utils import predict_to_series, prepare_panel, split_xy


@register("TabNetModel")
class TabNetModel(ModelFT):
    """Optional heavy dep — requires ``pytorch-tabnet``."""

    def __init__(
        self,
        n_d: int = 16,
        n_a: int = 16,
        n_steps: int = 3,
        gamma: float = 1.3,
        lambda_sparse: float = 1e-3,
        max_epochs: int = 30,
        batch_size: int = 1024,
        virtual_batch_size: int = 128,
        patience: int = 10,
        device: str = "auto",
        **extra: Any,
    ) -> None:
        self.params = {
            "n_d": int(n_d),
            "n_a": int(n_a),
            "n_steps": int(n_steps),
            "gamma": float(gamma),
            "lambda_sparse": float(lambda_sparse),
            **extra,
        }
        self.max_epochs = int(max_epochs)
        self.batch_size = int(batch_size)
        self.virtual_batch_size = int(virtual_batch_size)
        self.patience = int(patience)
        self.device = device
        self.model: Any | None = None

    def _import_tabnet(self):
        try:
            from pytorch_tabnet.tab_model import TabNetRegressor
        except ImportError as e:  # pragma: no cover
            raise ImportError(
                "pytorch-tabnet is not installed. Install with `pip install -e \".[ml-torch]\"`"
            ) from e
        return TabNetRegressor

    def fit(self, dataset: Any, reweighter: Reweighter | None = None) -> TabNetModel:
        TabNetRegressor = self._import_tabnet()
        panel = prepare_panel(dataset, "train")
        X, y, _ = split_xy(panel)
        y = y.reshape(-1, 1)
        eval_set = None
        try:
            vp = prepare_panel(dataset, "valid")
            Xv, yv, _ = split_xy(vp)
            eval_set = [(Xv, yv.reshape(-1, 1))]
        except Exception:
            pass
        device_name = self.device if self.device != "auto" else None
        self.model = TabNetRegressor(device_name=device_name, **self.params)
        self.model.fit(
            X_train=X,
            y_train=y,
            eval_set=eval_set,
            max_epochs=self.max_epochs,
            batch_size=self.batch_size,
            virtual_batch_size=self.virtual_batch_size,
            patience=self.patience,
        )
        return self

    def finetune(self, dataset: Any) -> TabNetModel:
        return self.fit(dataset)

    def predict(self, dataset: Any, segment: str | slice = "test") -> pd.Series:
        if self.model is None:
            raise RuntimeError("TabNetModel.predict called before fit().")
        seg = segment if isinstance(segment, str) else "test"
        panel = prepare_panel(dataset, seg)
        X, _, _ = split_xy(panel)
        preds = self.model.predict(X).reshape(-1)
        return predict_to_series(dataset, seg, np.asarray(preds))
