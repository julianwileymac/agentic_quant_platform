"""Keras 3 / TensorFlow-backed model adapters."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from aqp.core.registry import register
from aqp.ml.base import Model, Reweighter
from aqp.ml.models._utils import predict_to_series, prepare_panel, split_xy


def _import_keras() -> Any:
    try:
        import keras

        return keras
    except Exception:
        try:
            from tensorflow import keras  # type: ignore

            return keras
        except Exception as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "Keras/TensorFlow is not installed. Install `ml-keras` or `ml-tensorflow`."
            ) from exc


class _KerasSerializableMixin:
    def __getstate__(self) -> dict[str, Any]:
        state = dict(self.__dict__)
        model = state.pop("model_", None)
        state["_keras_model_json"] = None
        state["_keras_weights"] = None
        if model is not None:
            try:
                state["_keras_model_json"] = model.to_json()
                state["_keras_weights"] = model.get_weights()
            except Exception:
                state["_keras_model_json"] = None
                state["_keras_weights"] = None
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        model_json = state.pop("_keras_model_json", None)
        weights = state.pop("_keras_weights", None)
        self.__dict__.update(state)
        self.model_ = None
        if model_json:
            try:
                keras = _import_keras()
                self.model_ = keras.models.model_from_json(model_json)
                self.model_.compile(optimizer=self.optimizer, loss=self.loss)
                if weights is not None:
                    self.model_.set_weights(weights)
            except Exception:
                self.model_ = None


@register("KerasMLPModel")
class KerasMLPModel(_KerasSerializableMixin, Model):
    """Small dense Keras regressor for tabular/panel alpha experiments."""

    def __init__(
        self,
        hidden_layers: list[int] | None = None,
        dropout: float = 0.0,
        activation: str = "relu",
        optimizer: str = "adam",
        loss: str = "mse",
        epochs: int = 20,
        batch_size: int = 128,
        validation_segment: str | None = "valid",
        verbose: int = 0,
    ) -> None:
        self.hidden_layers = list(hidden_layers or [128, 64])
        self.dropout = float(dropout)
        self.activation = str(activation)
        self.optimizer = str(optimizer)
        self.loss = str(loss)
        self.epochs = int(epochs)
        self.batch_size = int(batch_size)
        self.validation_segment = validation_segment
        self.verbose = int(verbose)
        self.model_: Any | None = None
        self.feature_names_: list[str] = []
        self.history_: dict[str, Any] = {}

    def _build(self, input_dim: int) -> Any:
        keras = _import_keras()
        layers = [keras.layers.Input(shape=(input_dim,))]
        for width in self.hidden_layers:
            layers.append(keras.layers.Dense(int(width), activation=self.activation))
            if self.dropout > 0:
                layers.append(keras.layers.Dropout(self.dropout))
        layers.append(keras.layers.Dense(1))
        model = keras.Sequential(layers)
        model.compile(optimizer=self.optimizer, loss=self.loss)
        return model

    def fit(self, dataset: Any, reweighter: Reweighter | None = None) -> KerasMLPModel:
        panel = prepare_panel(dataset, "train")
        X, y, features = split_xy(panel)
        self.feature_names_ = features
        self.model_ = self._build(X.shape[1])
        sw = reweighter.reweight(X) if reweighter else None
        validation_data = None
        if self.validation_segment:
            try:
                valid = prepare_panel(dataset, self.validation_segment)
                Xv, yv, _ = split_xy(valid)
                validation_data = (Xv, yv)
            except Exception:
                validation_data = None
        hist = self.model_.fit(
            X,
            y,
            sample_weight=sw,
            validation_data=validation_data,
            epochs=self.epochs,
            batch_size=self.batch_size,
            verbose=self.verbose,
        )
        self.history_ = {k: [float(x) for x in v] for k, v in getattr(hist, "history", {}).items()}
        return self

    def predict(self, dataset: Any, segment: str | slice = "test") -> pd.Series:
        if self.model_ is None:
            raise RuntimeError("KerasMLPModel.predict called before fit().")
        seg = segment if isinstance(segment, str) else "test"
        panel = prepare_panel(dataset, seg)
        X, _, _ = split_xy(panel)
        preds = np.asarray(self.model_.predict(X, verbose=0), dtype=float).reshape(-1)
        return predict_to_series(dataset, seg, preds)


@register("KerasLSTMModel")
class KerasLSTMModel(KerasMLPModel):
    """Keras LSTM regressor for ``TSDatasetH`` windows."""

    def __init__(
        self,
        hidden_size: int = 64,
        recurrent_layers: int = 1,
        dropout: float = 0.0,
        optimizer: str = "adam",
        loss: str = "mse",
        epochs: int = 20,
        batch_size: int = 128,
        validation_segment: str | None = "valid",
        verbose: int = 0,
    ) -> None:
        super().__init__(
            hidden_layers=[],
            dropout=dropout,
            optimizer=optimizer,
            loss=loss,
            epochs=epochs,
            batch_size=batch_size,
            validation_segment=validation_segment,
            verbose=verbose,
        )
        self.hidden_size = int(hidden_size)
        self.recurrent_layers = int(recurrent_layers)

    def _sampler_xy(self, sampler: Any) -> tuple[np.ndarray, np.ndarray, pd.MultiIndex]:
        X_rows = []
        y_rows = []
        for i in range(len(sampler)):
            x, y = sampler[i]
            X_rows.append(x)
            y_rows.append(y)
        return (
            np.asarray(X_rows, dtype=np.float32),
            np.asarray(y_rows, dtype=np.float32),
            sampler.get_index(),
        )

    def _build_sequence(self, step_len: int, input_dim: int) -> Any:
        keras = _import_keras()
        layers = [keras.layers.Input(shape=(step_len, input_dim))]
        for i in range(max(1, self.recurrent_layers)):
            layers.append(
                keras.layers.LSTM(
                    self.hidden_size,
                    return_sequences=i < self.recurrent_layers - 1,
                )
            )
            if self.dropout > 0:
                layers.append(keras.layers.Dropout(self.dropout))
        layers.append(keras.layers.Dense(1))
        model = keras.Sequential(layers)
        model.compile(optimizer=self.optimizer, loss=self.loss)
        return model

    def fit(self, dataset: Any, reweighter: Reweighter | None = None) -> KerasLSTMModel:
        del reweighter
        sampler = dataset.prepare("train")
        X, y, _ = self._sampler_xy(sampler)
        self.model_ = self._build_sequence(X.shape[1], X.shape[2])
        validation_data = None
        if self.validation_segment:
            try:
                Xv, yv, _ = self._sampler_xy(dataset.prepare(self.validation_segment))
                validation_data = (Xv, yv)
            except Exception:
                validation_data = None
        hist = self.model_.fit(
            X,
            y,
            validation_data=validation_data,
            epochs=self.epochs,
            batch_size=self.batch_size,
            verbose=self.verbose,
        )
        self.history_ = {k: [float(x) for x in v] for k, v in getattr(hist, "history", {}).items()}
        return self

    def predict(self, dataset: Any, segment: str | slice = "test") -> pd.Series:
        if self.model_ is None:
            raise RuntimeError("KerasLSTMModel.predict called before fit().")
        seg = segment if isinstance(segment, str) else "test"
        X, _, idx = self._sampler_xy(dataset.prepare(seg))
        preds = np.asarray(self.model_.predict(X, verbose=0), dtype=float).reshape(-1)
        return pd.Series(preds, index=idx, name="score")


@register("KerasFunctionalModel", kind="model")
class KerasFunctionalModel(_KerasSerializableMixin, Model):
    """Multi-input Keras Functional API model.

    Accepts a list of feature blocks (each a list of column-name patterns)
    and an optional ``trunk`` definition. Each block flows through its own
    sub-network (dense+dropout) before concatenation into a shared trunk.

    Useful for separating numeric features from categorical embeddings or
    combining wide and deep paths in a single network.
    """

    def __init__(
        self,
        feature_blocks: list[dict[str, Any]] | None = None,
        trunk_layers: list[int] | None = None,
        dropout: float = 0.1,
        activation: str = "relu",
        optimizer: str = "adam",
        loss: str = "mse",
        epochs: int = 30,
        batch_size: int = 256,
        validation_segment: str | None = "valid",
        verbose: int = 0,
    ) -> None:
        # Default to a single block touching all features and a 64-32 trunk.
        self.feature_blocks = list(feature_blocks or [{"name": "all", "hidden_layers": [64]}])
        self.trunk_layers = list(trunk_layers or [64, 32])
        self.dropout = float(dropout)
        self.activation = str(activation)
        self.optimizer = str(optimizer)
        self.loss = str(loss)
        self.epochs = int(epochs)
        self.batch_size = int(batch_size)
        self.validation_segment = validation_segment
        self.verbose = int(verbose)
        self.model_: Any | None = None
        self.feature_names_: list[str] = []
        self.history_: dict[str, Any] = {}
        self._block_indices: list[list[int]] = []

    def _resolve_blocks(self, features: list[str]) -> list[list[int]]:
        import re

        out: list[list[int]] = []
        for block in self.feature_blocks:
            patterns = block.get("columns") or block.get("patterns")
            if not patterns:
                # No filter -> use all columns for this block
                out.append(list(range(len(features))))
                continue
            indices: list[int] = []
            for idx, name in enumerate(features):
                for pat in patterns:
                    if re.search(str(pat), name):
                        indices.append(idx)
                        break
            if not indices:
                indices = list(range(len(features)))
            out.append(indices)
        return out

    def _build(self, features: list[str]) -> Any:
        keras = _import_keras()
        layers = keras.layers
        block_indices = self._resolve_blocks(features)
        self._block_indices = block_indices

        inputs: list[Any] = []
        block_outputs: list[Any] = []
        for block, indices in zip(self.feature_blocks, block_indices, strict=False):
            inp = layers.Input(shape=(len(indices),), name=str(block.get("name") or "block"))
            x = inp
            for width in block.get("hidden_layers") or [32]:
                x = layers.Dense(int(width), activation=self.activation)(x)
                if self.dropout > 0:
                    x = layers.Dropout(self.dropout)(x)
            inputs.append(inp)
            block_outputs.append(x)

        if len(block_outputs) == 1:
            trunk = block_outputs[0]
        else:
            trunk = layers.Concatenate()(block_outputs)
        for width in self.trunk_layers:
            trunk = layers.Dense(int(width), activation=self.activation)(trunk)
            if self.dropout > 0:
                trunk = layers.Dropout(self.dropout)(trunk)
        out = layers.Dense(1)(trunk)

        model = keras.Model(inputs=inputs, outputs=out)
        model.compile(optimizer=self.optimizer, loss=self.loss)
        return model

    def _split_inputs(self, X: np.ndarray) -> list[np.ndarray]:
        return [X[:, indices] for indices in self._block_indices]

    def fit(self, dataset: Any, reweighter: Reweighter | None = None) -> KerasFunctionalModel:
        del reweighter
        panel = prepare_panel(dataset, "train")
        X, y, features = split_xy(panel)
        self.feature_names_ = features
        self.model_ = self._build(features)
        validation_data = None
        if self.validation_segment:
            try:
                valid = prepare_panel(dataset, self.validation_segment)
                Xv, yv, _ = split_xy(valid)
                validation_data = (self._split_inputs(Xv), yv)
            except Exception:
                validation_data = None
        hist = self.model_.fit(
            self._split_inputs(X),
            y,
            validation_data=validation_data,
            epochs=self.epochs,
            batch_size=self.batch_size,
            verbose=self.verbose,
        )
        self.history_ = {k: [float(x) for x in v] for k, v in getattr(hist, "history", {}).items()}
        return self

    def predict(self, dataset: Any, segment: str | slice = "test") -> pd.Series:
        if self.model_ is None:
            raise RuntimeError("KerasFunctionalModel.predict called before fit().")
        seg = segment if isinstance(segment, str) else "test"
        panel = prepare_panel(dataset, seg)
        X, _, _ = split_xy(panel)
        preds = np.asarray(
            self.model_.predict(self._split_inputs(X), verbose=0), dtype=float
        ).reshape(-1)
        return predict_to_series(dataset, seg, preds)


@register("KerasTabTransformerModel", kind="model")
class KerasTabTransformerModel(_KerasSerializableMixin, Model):
    """A small TabTransformer-style model in pure Keras.

    Treats numeric features as a token sequence projected through a stack
    of self-attention blocks. Default hyperparameters are deliberately
    modest so the model trains quickly on small alpha panels; expose
    ``num_heads`` / ``ff_dim`` / ``num_blocks`` via YAML for tuning.
    """

    def __init__(
        self,
        embed_dim: int = 16,
        num_heads: int = 2,
        num_blocks: int = 2,
        ff_dim: int = 32,
        dropout: float = 0.1,
        optimizer: str = "adam",
        loss: str = "mse",
        epochs: int = 30,
        batch_size: int = 128,
        validation_segment: str | None = "valid",
        verbose: int = 0,
    ) -> None:
        self.embed_dim = int(embed_dim)
        self.num_heads = int(num_heads)
        self.num_blocks = int(num_blocks)
        self.ff_dim = int(ff_dim)
        self.dropout = float(dropout)
        self.optimizer = str(optimizer)
        self.loss = str(loss)
        self.epochs = int(epochs)
        self.batch_size = int(batch_size)
        self.validation_segment = validation_segment
        self.verbose = int(verbose)
        self.model_: Any | None = None
        self.feature_names_: list[str] = []
        self.history_: dict[str, Any] = {}

    def _build(self, num_features: int) -> Any:
        keras = _import_keras()
        layers = keras.layers
        inp = layers.Input(shape=(num_features,))
        # Project each scalar feature into ``embed_dim`` token embedding.
        tokens = layers.Reshape((num_features, 1))(inp)
        tokens = layers.Dense(self.embed_dim)(tokens)
        x = tokens
        for _ in range(self.num_blocks):
            attn = layers.MultiHeadAttention(
                num_heads=self.num_heads, key_dim=self.embed_dim
            )(x, x)
            x = layers.LayerNormalization(epsilon=1e-6)(x + attn)
            ffn = layers.Dense(self.ff_dim, activation="gelu")(x)
            ffn = layers.Dense(self.embed_dim)(ffn)
            x = layers.LayerNormalization(epsilon=1e-6)(x + ffn)
            if self.dropout > 0:
                x = layers.Dropout(self.dropout)(x)
        x = layers.GlobalAveragePooling1D()(x)
        x = layers.Dense(self.ff_dim, activation="relu")(x)
        if self.dropout > 0:
            x = layers.Dropout(self.dropout)(x)
        out = layers.Dense(1)(x)
        model = keras.Model(inputs=inp, outputs=out)
        model.compile(optimizer=self.optimizer, loss=self.loss)
        return model

    def fit(self, dataset: Any, reweighter: Reweighter | None = None) -> KerasTabTransformerModel:
        del reweighter
        panel = prepare_panel(dataset, "train")
        X, y, features = split_xy(panel)
        self.feature_names_ = features
        self.model_ = self._build(X.shape[1])
        validation_data = None
        if self.validation_segment:
            try:
                valid = prepare_panel(dataset, self.validation_segment)
                Xv, yv, _ = split_xy(valid)
                validation_data = (Xv, yv)
            except Exception:
                validation_data = None
        hist = self.model_.fit(
            X,
            y,
            validation_data=validation_data,
            epochs=self.epochs,
            batch_size=self.batch_size,
            verbose=self.verbose,
        )
        self.history_ = {k: [float(x) for x in v] for k, v in getattr(hist, "history", {}).items()}
        return self

    def predict(self, dataset: Any, segment: str | slice = "test") -> pd.Series:
        if self.model_ is None:
            raise RuntimeError("KerasTabTransformerModel.predict called before fit().")
        seg = segment if isinstance(segment, str) else "test"
        panel = prepare_panel(dataset, seg)
        X, _, _ = split_xy(panel)
        preds = np.asarray(self.model_.predict(X, verbose=0), dtype=float).reshape(-1)
        return predict_to_series(dataset, seg, preds)


__all__ = [
    "KerasFunctionalModel",
    "KerasLSTMModel",
    "KerasMLPModel",
    "KerasTabTransformerModel",
]
