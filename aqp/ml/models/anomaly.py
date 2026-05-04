"""Anomaly detection models for quant ML workflows."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from aqp.core.registry import register
from aqp.ml.base import Model, Reweighter
from aqp.ml.models._utils import predict_to_series, prepare_panel, split_xy


@register("PyODAnomalyModel", kind="model")
class PyODAnomalyModel(Model):
    """Wrap PyOD detectors and return anomaly scores as model predictions.

    Supported detectors (string keys): ``iforest``, ``knn``, ``ecod``,
    ``copod``, ``lof``, ``suod``, ``auto_encoder``, ``hbos``, ``mcd``,
    ``ocsvm``, ``pca``. Additional detectors can be plugged in by passing
    ``detector_cls`` (a fully imported class) directly via
    ``detector_kwargs={"_cls": ...}``.
    """

    def __init__(
        self,
        detector: str = "iforest",
        contamination: float = 0.02,
        detector_kwargs: dict[str, Any] | None = None,
        invert_score: bool = False,
    ) -> None:
        self.detector_name = detector.lower()
        self.contamination = float(contamination)
        self.detector_kwargs = dict(detector_kwargs or {})
        self.invert_score = bool(invert_score)
        self.detector_: Any | None = None
        self.feature_names_: list[str] = []

    def _make_detector(self) -> Any:
        try:
            if self.detector_name == "iforest":
                from pyod.models.iforest import IForest

                return IForest(contamination=self.contamination, **self.detector_kwargs)
            if self.detector_name == "knn":
                from pyod.models.knn import KNN

                return KNN(contamination=self.contamination, **self.detector_kwargs)
            if self.detector_name == "ecod":
                from pyod.models.ecod import ECOD

                return ECOD(contamination=self.contamination, **self.detector_kwargs)
            if self.detector_name == "copod":
                from pyod.models.copod import COPOD

                return COPOD(contamination=self.contamination, **self.detector_kwargs)
            if self.detector_name == "lof":
                from pyod.models.lof import LOF

                return LOF(contamination=self.contamination, **self.detector_kwargs)
            if self.detector_name == "suod":
                from pyod.models.suod import SUOD

                # SUOD takes a list of base estimators; default to a small ensemble.
                base = self.detector_kwargs.pop("base_estimators", None)
                if base is None:
                    from pyod.models.copod import COPOD
                    from pyod.models.iforest import IForest
                    from pyod.models.lof import LOF

                    base = [LOF(), IForest(), COPOD()]
                return SUOD(
                    base_estimators=base,
                    contamination=self.contamination,
                    **self.detector_kwargs,
                )
            if self.detector_name in {"auto_encoder", "autoencoder"}:
                # PyOD's AutoEncoder requires a TF/Keras backend.
                from pyod.models.auto_encoder import AutoEncoder

                return AutoEncoder(
                    contamination=self.contamination,
                    **self.detector_kwargs,
                )
            if self.detector_name == "hbos":
                from pyod.models.hbos import HBOS

                return HBOS(contamination=self.contamination, **self.detector_kwargs)
            if self.detector_name == "mcd":
                from pyod.models.mcd import MCD

                return MCD(contamination=self.contamination, **self.detector_kwargs)
            if self.detector_name == "ocsvm":
                from pyod.models.ocsvm import OCSVM

                return OCSVM(contamination=self.contamination, **self.detector_kwargs)
            if self.detector_name == "pca":
                from pyod.models.pca import PCA

                return PCA(contamination=self.contamination, **self.detector_kwargs)
        except ImportError as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "pyod is not installed. Install the `ml-anomaly` extra."
            ) from exc
        raise ValueError(f"Unknown PyOD detector {self.detector_name!r}")

    def fit(self, dataset: Any, reweighter: Reweighter | None = None) -> PyODAnomalyModel:
        del reweighter
        panel = prepare_panel(dataset, "train")
        X, _, features = split_xy(panel)
        self.feature_names_ = features
        self.detector_ = self._make_detector()
        self.detector_.fit(np.nan_to_num(X))
        return self

    def predict(self, dataset: Any, segment: str | slice = "test") -> pd.Series:
        if self.detector_ is None:
            raise RuntimeError("PyODAnomalyModel.predict called before fit().")
        seg = segment if isinstance(segment, str) else "test"
        panel = prepare_panel(dataset, seg)
        X, _, _ = split_xy(panel)
        X = np.nan_to_num(X)
        if hasattr(self.detector_, "decision_function"):
            scores = np.asarray(self.detector_.decision_function(X), dtype=float)
        elif hasattr(self.detector_, "decision_scores_"):
            scores = np.asarray(self.detector_.decision_scores_, dtype=float)[: len(X)]
        else:
            labels = np.asarray(self.detector_.predict(X), dtype=float)
            scores = labels
        if self.invert_score:
            scores = -scores
        return predict_to_series(dataset, seg, scores.reshape(-1))


__all__ = ["PyODAnomalyModel"]
