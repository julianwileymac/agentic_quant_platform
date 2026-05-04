"""Native TensorFlow estimator adapters.

Separate from the Keras 3 wrappers in :mod:`aqp.ml.models.keras` because TF's
``tf.estimator`` API has its own input-fn / saved-model contract that
benefits from a dedicated adapter. Gated behind ``settings.tf_native_enabled``
so importing the module on a Keras-only install does not crash.

Three estimators are exposed under one wrapper:

- ``linear`` — :class:`tf.estimator.LinearRegressor`
- ``dnn`` — :class:`tf.estimator.DNNRegressor`
- ``boosted_trees`` — :class:`tf.estimator.BoostedTreesRegressor`
"""
from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aqp.config import settings
from aqp.core.registry import register
from aqp.ml.base import Model, Reweighter
from aqp.ml.models._utils import predict_to_series, prepare_panel, split_xy

logger = logging.getLogger(__name__)


def _ensure_enabled() -> None:
    if not getattr(settings, "tf_native_enabled", False):
        raise RuntimeError(
            "Native TensorFlow estimator support is disabled. "
            "Set AQP_TF_NATIVE_ENABLED=true and install the `ml-tensorflow` extra."
        )


def _import_tf() -> Any:
    try:
        import tensorflow as tf  # type: ignore

        return tf
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "TensorFlow is not installed. Install the `ml-tensorflow` extra."
        ) from exc


@register("TFEstimatorModel", kind="model")
class TFEstimatorModel(Model):
    """Wrap a ``tf.estimator`` regressor in the AQP ``Model`` contract.

    The estimator type is selected via the ``estimator`` string. We export
    a ``SavedModel`` directory under :class:`__getstate__` so the model
    survives ``Serializable.to_pickle`` / ``from_pickle``.
    """

    SUPPORTED = {"linear", "dnn", "boosted_trees"}

    def __init__(
        self,
        estimator: str = "dnn",
        hidden_units: list[int] | None = None,
        n_trees: int = 64,
        learning_rate: float = 0.05,
        max_depth: int = 4,
        n_batches_per_layer: int = 1,
        steps: int = 1000,
        batch_size: int = 256,
        model_dir: str | Path | None = None,
    ) -> None:
        _ensure_enabled()
        if estimator not in self.SUPPORTED:
            raise ValueError(f"estimator must be one of {self.SUPPORTED}")
        self.estimator_kind = estimator
        self.hidden_units = list(hidden_units or [64, 32])
        self.n_trees = int(n_trees)
        self.learning_rate = float(learning_rate)
        self.max_depth = int(max_depth)
        self.n_batches_per_layer = int(n_batches_per_layer)
        self.steps = int(steps)
        self.batch_size = int(batch_size)
        self.model_dir = Path(model_dir) if model_dir else Path(tempfile.mkdtemp(prefix="tf_estimator_"))
        self.estimator_: Any | None = None
        self.feature_names_: list[str] = []
        self._saved_model_bytes: bytes | None = None

    def _build_estimator(self, num_features: int) -> Any:
        tf = _import_tf()
        feature_columns = [
            tf.feature_column.numeric_column(f"f{i}") for i in range(num_features)
        ]
        if self.estimator_kind == "linear":
            return tf.estimator.LinearRegressor(
                feature_columns=feature_columns, model_dir=str(self.model_dir)
            )
        if self.estimator_kind == "dnn":
            return tf.estimator.DNNRegressor(
                feature_columns=feature_columns,
                hidden_units=self.hidden_units,
                model_dir=str(self.model_dir),
            )
        # boosted_trees
        return tf.estimator.BoostedTreesRegressor(
            feature_columns=feature_columns,
            n_batches_per_layer=self.n_batches_per_layer,
            n_trees=self.n_trees,
            max_depth=self.max_depth,
            learning_rate=self.learning_rate,
            model_dir=str(self.model_dir),
        )

    def _make_input_fn(self, X: np.ndarray, y: np.ndarray | None, *, shuffle: bool):
        tf = _import_tf()
        features = {f"f{i}": X[:, i].astype(np.float32) for i in range(X.shape[1])}

        def _input_fn():
            ds = tf.data.Dataset.from_tensor_slices(
                (features, y.astype(np.float32)) if y is not None else features
            )
            if shuffle:
                ds = ds.shuffle(buffer_size=max(1024, len(X)))
            ds = ds.batch(self.batch_size)
            return ds

        return _input_fn

    def fit(self, dataset: Any, reweighter: Reweighter | None = None) -> TFEstimatorModel:
        del reweighter
        panel = prepare_panel(dataset, "train")
        X, y, features = split_xy(panel)
        self.feature_names_ = features
        self.estimator_ = self._build_estimator(X.shape[1])
        self.estimator_.train(
            input_fn=self._make_input_fn(X, y, shuffle=True), steps=self.steps
        )
        return self

    def predict(self, dataset: Any, segment: str | slice = "test") -> pd.Series:
        if self.estimator_ is None:
            raise RuntimeError("TFEstimatorModel.predict called before fit().")
        seg = segment if isinstance(segment, str) else "test"
        panel = prepare_panel(dataset, seg)
        X, _, _ = split_xy(panel)
        preds_iter = self.estimator_.predict(input_fn=self._make_input_fn(X, None, shuffle=False))
        scores: list[float] = []
        for record in preds_iter:
            value = record.get("predictions", record.get("class_ids"))
            if value is None:
                continue
            scores.append(float(np.asarray(value, dtype=float).reshape(-1)[0]))
        if len(scores) < len(X):
            scores.extend([0.0] * (len(X) - len(scores)))
        return predict_to_series(dataset, seg, np.asarray(scores[: len(X)], dtype=float))

    # ------------------------------------------------------------------
    # Serialization (zip-the-model-dir-into-bytes pattern for pickleability)
    # ------------------------------------------------------------------

    def __getstate__(self) -> dict[str, Any]:
        state = dict(self.__dict__)
        state.pop("estimator_", None)
        if Path(self.model_dir).exists():
            try:
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
                tmp.close()
                archive = shutil.make_archive(
                    base_name=tmp.name.rstrip(".zip"),
                    format="zip",
                    root_dir=str(self.model_dir),
                )
                state["_model_dir_bytes"] = Path(archive).read_bytes()
                Path(archive).unlink(missing_ok=True)
            except Exception:
                logger.debug("TFEstimatorModel pickle skipped (model dir)", exc_info=True)
                state["_model_dir_bytes"] = None
        else:
            state["_model_dir_bytes"] = None
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        blob = state.pop("_model_dir_bytes", None)
        self.__dict__.update(state)
        self.estimator_ = None
        if blob:
            try:
                target = Path(tempfile.mkdtemp(prefix="tf_estimator_restored_"))
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
                tmp.write(blob)
                tmp.close()
                shutil.unpack_archive(tmp.name, str(target))
                Path(tmp.name).unlink(missing_ok=True)
                self.model_dir = target
                if self.feature_names_:
                    self.estimator_ = self._build_estimator(len(self.feature_names_))
            except Exception:
                logger.debug("TFEstimatorModel restore skipped", exc_info=True)


__all__ = ["TFEstimatorModel"]
