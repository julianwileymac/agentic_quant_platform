"""Ensemble models — ``DEnsembleModel`` (Double Ensemble), stacking ensembles.

Reference: ``inspiration/qlib-main/qlib/contrib/model/double_ensemble.py`` and
``inspiration/Stock-Prediction-Models-master/stacking/``.

* :class:`DEnsembleModel` — LightGBM bagging over random feature subsets.
* :class:`ARIMAXGBStack` — stack an ARIMA residual with an XGBoost booster
  (Stock-Prediction-Models stacking notebook pattern).
* :class:`AutoEncoderDNNStack` — compress features through a dense
  auto-encoder, then feed the bottleneck into a small DNN / LightGBM
  regressor on top.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from aqp.core.registry import register
from aqp.ml.base import Model
from aqp.ml.models._utils import predict_to_series, prepare_panel, split_xy

logger = logging.getLogger(__name__)


@register("DEnsembleModel")
class DEnsembleModel(Model):
    """Double-ensemble of LightGBM boosters (feature bagging)."""

    def __init__(
        self,
        n_models: int = 6,
        feature_fraction: float = 0.7,
        sample_fraction: float = 0.8,
        seed: int = 42,
        **booster_kwargs: Any,
    ) -> None:
        self.n_models = int(n_models)
        self.feature_fraction = float(feature_fraction)
        self.sample_fraction = float(sample_fraction)
        self.seed = int(seed)
        self.booster_kwargs = {
            "n_estimators": 200,
            "learning_rate": 0.05,
            "num_leaves": 31,
            "verbose": -1,
            **booster_kwargs,
        }
        self.models_: list[Any] = []
        self.feature_masks_: list[np.ndarray] = []

    def fit(self, dataset: Any, reweighter: Any | None = None) -> DEnsembleModel:
        import lightgbm as lgb

        rng = np.random.default_rng(self.seed)
        panel = prepare_panel(dataset, "train")
        X, y, _ = split_xy(panel)
        n_samples, n_feats = X.shape

        self.models_.clear()
        self.feature_masks_.clear()
        n_pick = max(1, int(round(self.feature_fraction * n_feats)))
        n_rows = max(1, int(round(self.sample_fraction * n_samples)))

        for i in range(self.n_models):
            feat_idx = rng.choice(n_feats, size=n_pick, replace=False)
            row_idx = rng.choice(n_samples, size=n_rows, replace=True)
            sub_X = X[row_idx][:, feat_idx]
            sub_y = y[row_idx]
            booster = lgb.LGBMRegressor(random_state=self.seed + i, **self.booster_kwargs)
            booster.fit(sub_X, sub_y)
            self.models_.append(booster)
            self.feature_masks_.append(feat_idx)
        return self

    def predict(self, dataset: Any, segment: str | slice = "test") -> pd.Series:
        if not self.models_:
            raise RuntimeError("DEnsembleModel.predict called before fit().")
        seg = segment if isinstance(segment, str) else "test"
        panel = prepare_panel(dataset, seg)
        X, _, _ = split_xy(panel)
        preds = np.zeros(X.shape[0], dtype=float)
        for booster, mask in zip(self.models_, self.feature_masks_, strict=False):
            preds += booster.predict(X[:, mask])
        preds /= max(1, len(self.models_))
        return predict_to_series(dataset, seg, preds)


# ---------------------------------------------------------------------------
# Stacking ensembles (Stock-Prediction-Models)
# ---------------------------------------------------------------------------


@register("ARIMAXGBStack")
class ARIMAXGBStack(Model):
    """Stack an ARIMA trend estimator with an XGBoost residual booster.

    Pipeline:

    1. Fit ARIMA(p,d,q) on the label series directly.
    2. Feed ARIMA's in-sample residuals as one additional feature to
       XGBoost; XGBoost's prediction is added back to the ARIMA forecast
       at inference time.
    """

    def __init__(
        self,
        arima_order: tuple[int, int, int] = (1, 1, 1),
        xgb_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self.arima_order = tuple(arima_order)
        self.xgb_kwargs = {
            "n_estimators": 300,
            "learning_rate": 0.05,
            "max_depth": 5,
            "verbosity": 0,
            **(xgb_kwargs or {}),
        }
        self.arima_: Any = None
        self.xgb_: Any = None
        self._label_mean: float = 0.0

    def fit(self, dataset: Any, reweighter: Any | None = None) -> ARIMAXGBStack:
        import xgboost as xgb
        from statsmodels.tsa.arima.model import ARIMA

        panel = prepare_panel(dataset, "train")
        X, y, _ = split_xy(panel)
        self._label_mean = float(y.mean()) if len(y) else 0.0

        try:
            arima = ARIMA(pd.Series(y), order=self.arima_order, trend="c").fit()
            residuals = y - np.asarray(arima.fittedvalues)
            self.arima_ = arima
        except Exception:
            logger.exception("ARIMA fit failed; falling back to mean residual.")
            residuals = y - self._label_mean
            self.arima_ = None

        extra = np.asarray(residuals).reshape(-1, 1)
        X_aug = np.concatenate([X, extra], axis=1)
        self.xgb_ = xgb.XGBRegressor(**self.xgb_kwargs)
        self.xgb_.fit(X_aug, y)
        return self

    def predict(self, dataset: Any, segment: str | slice = "test") -> pd.Series:
        if self.xgb_ is None:
            raise RuntimeError("ARIMAXGBStack.predict called before fit().")
        seg = segment if isinstance(segment, str) else "test"
        panel = prepare_panel(dataset, seg)
        X, _, _ = split_xy(panel)
        if self.arima_ is not None:
            try:
                trend = np.asarray(self.arima_.forecast(steps=X.shape[0]))
            except Exception:
                trend = np.full(X.shape[0], self._label_mean, dtype=float)
        else:
            trend = np.full(X.shape[0], self._label_mean, dtype=float)
        extra = (np.zeros(X.shape[0]) - trend).reshape(-1, 1)
        X_aug = np.concatenate([X, extra], axis=1)
        residual_pred = np.asarray(self.xgb_.predict(X_aug))
        preds = trend + residual_pred
        return predict_to_series(dataset, seg, preds)


@register("AutoEncoderDNNStack")
class AutoEncoderDNNStack(Model):
    """Denoising auto-encoder → bottleneck → LightGBM booster.

    Common bench-mark in Stock-Prediction-Models: a small dense auto-encoder
    learns a compact representation of the raw features, and a downstream
    booster predicts the label from the bottleneck activations.
    """

    def __init__(
        self,
        bottleneck_dim: int = 16,
        hidden_dim: int = 64,
        epochs: int = 30,
        lr: float = 1e-3,
        lgb_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self.bottleneck_dim = int(bottleneck_dim)
        self.hidden_dim = int(hidden_dim)
        self.epochs = int(epochs)
        self.lr = float(lr)
        self.lgb_kwargs = {"n_estimators": 200, "learning_rate": 0.05, "verbose": -1, **(lgb_kwargs or {})}
        self.encoder_: Any = None
        self.booster_: Any = None

    def _build_ae(self, input_size: int, torch: Any):
        nn = torch.nn
        bottleneck = self.bottleneck_dim
        hidden = self.hidden_dim

        class _AutoEncoder(nn.Module):
            def __init__(self):
                super().__init__()
                self.encoder = nn.Sequential(
                    nn.Linear(input_size, hidden),
                    nn.ReLU(),
                    nn.Linear(hidden, bottleneck),
                )
                self.decoder = nn.Sequential(
                    nn.Linear(bottleneck, hidden),
                    nn.ReLU(),
                    nn.Linear(hidden, input_size),
                )

            def forward(self, x):
                z = self.encoder(x)
                return z, self.decoder(z)

        return _AutoEncoder()

    def _fit_autoencoder(self, X: np.ndarray) -> Any:
        try:
            import torch
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("torch is required for AutoEncoderDNNStack.") from exc
        model = self._build_ae(X.shape[1], torch)
        opt = torch.optim.Adam(model.parameters(), lr=self.lr)
        X_t = torch.tensor(X, dtype=torch.float32)
        for _ in range(self.epochs):
            model.train()
            opt.zero_grad()
            _, x_hat = model(X_t)
            loss = torch.nn.functional.mse_loss(x_hat, X_t)
            loss.backward()
            opt.step()
        model.eval()
        return model

    def fit(self, dataset: Any, reweighter: Any | None = None) -> AutoEncoderDNNStack:
        import lightgbm as lgb

        panel = prepare_panel(dataset, "train")
        X, y, _ = split_xy(panel)
        self.encoder_ = self._fit_autoencoder(X)

        import torch

        with torch.no_grad():
            z, _ = self.encoder_(torch.tensor(X, dtype=torch.float32))
            Z = z.numpy()
        self.booster_ = lgb.LGBMRegressor(**self.lgb_kwargs)
        self.booster_.fit(Z, y)
        return self

    def predict(self, dataset: Any, segment: str | slice = "test") -> pd.Series:
        if self.encoder_ is None or self.booster_ is None:
            raise RuntimeError("AutoEncoderDNNStack.predict called before fit().")
        import torch

        seg = segment if isinstance(segment, str) else "test"
        panel = prepare_panel(dataset, seg)
        X, _, _ = split_xy(panel)
        with torch.no_grad():
            z, _ = self.encoder_(torch.tensor(X, dtype=torch.float32))
            Z = z.numpy()
        preds = np.asarray(self.booster_.predict(Z))
        return predict_to_series(dataset, seg, preds)


__all__ = ["ARIMAXGBStack", "AutoEncoderDNNStack", "DEnsembleModel"]
