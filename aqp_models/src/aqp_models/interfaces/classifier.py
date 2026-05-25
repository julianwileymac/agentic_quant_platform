"""Classifier — discrete probability distribution over a finite class set.

The report's third reference application: market-regime detection,
directional probability, sentiment polarity. Backed by any AQP model
that exposes either ``predict_proba`` (sklearn / XGBoost classifier),
``classify`` (custom), or ``predict`` returning logits / scores that
the wrapper softmax-normalises.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from aqp.core.registry import register
from aqp_models.interfaces.base import InterfaceMetadata, PolymorphicInterface


@dataclass(slots=True)
class ClassDistribution:
    """Structured output of :meth:`Classifier.classify`."""

    classes: list[str]
    probabilities: np.ndarray
    argmax: int
    metadata: InterfaceMetadata | None = None

    @property
    def predicted_class(self) -> str:
        if 0 <= self.argmax < len(self.classes):
            return self.classes[self.argmax]
        return str(self.argmax)

    def to_json(self) -> dict[str, Any]:
        arr = np.asarray(self.probabilities, dtype=float)
        return {
            "classes": list(self.classes),
            "probabilities": arr.reshape(-1).tolist(),
            "shape": list(arr.shape),
            "argmax": int(self.argmax),
            "predicted_class": self.predicted_class,
            "metadata": self.metadata.to_json() if self.metadata else None,
        }


@register("Classifier", kind="interface")
class Classifier(PolymorphicInterface):
    """Polymorphic wrapper for classification models.

    Resolution order (most -> least specific):

    1. ``model.classify(data)`` — when present, used directly.
    2. ``model.predict_proba(data)`` — sklearn / xgboost classifier path.
    3. ``model.predict(data)`` — treated as logits / scores and softmax-
       normalised. For binary outputs a sigmoid is applied first.

    The wrapper guarantees a normalised :class:`ClassDistribution` with
    a non-empty ``classes`` list. When the underlying model does not
    expose ``classes_`` the wrapper synthesises ``"class_0"`` etc.
    """

    interface_kind = "classifier"
    alias = "classifier"

    def __init__(
        self,
        *,
        model: Any,
        alias: str | None = None,
        classes: list[str] | None = None,
    ) -> None:
        super().__init__(model=model, alias=alias)
        self._configured_classes = list(classes) if classes else None

    def classify(self, data: Any, **kwargs: Any) -> ClassDistribution:
        started = datetime.utcnow()
        frame = _coerce_frame(data)

        # Path 1 — native classify
        if hasattr(self.model, "classify"):
            raw = self.model.classify(frame, **kwargs)
            probs = _to_probability_matrix(raw)
            classes = self._resolve_classes(probs.shape[1])
            argmax = int(np.argmax(probs[-1])) if probs.size else 0
            return ClassDistribution(
                classes=classes,
                probabilities=probs,
                argmax=argmax,
                metadata=self._build_metadata(
                    started=started, extras={"strategy": "native_classify"}
                ),
            )

        # Path 2 — predict_proba
        if hasattr(self.model, "predict_proba"):
            raw = self.model.predict_proba(frame, **kwargs)
            probs = _to_probability_matrix(raw)
            classes = self._resolve_classes(probs.shape[1])
            argmax = int(np.argmax(probs[-1])) if probs.size else 0
            return ClassDistribution(
                classes=classes,
                probabilities=probs,
                argmax=argmax,
                metadata=self._build_metadata(
                    started=started, extras={"strategy": "predict_proba"}
                ),
            )

        # Path 3 — predict returns logits / scores; normalise.
        raw = self._delegate_predict(frame, **kwargs)
        scores = _to_score_matrix(raw)
        probs = _softmax(scores)
        classes = self._resolve_classes(probs.shape[1])
        argmax = int(np.argmax(probs[-1])) if probs.size else 0
        return ClassDistribution(
            classes=classes,
            probabilities=probs,
            argmax=argmax,
            metadata=self._build_metadata(
                started=started,
                extras={"strategy": "softmax_from_predict"},
            ),
        )

    def supports(self, model: Any) -> bool:
        return (
            hasattr(model, "classify")
            or hasattr(model, "predict_proba")
            or hasattr(model, "predict")
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _resolve_classes(self, n_columns: int) -> list[str]:
        if self._configured_classes:
            return list(self._configured_classes[:n_columns])
        classes_attr = getattr(self.model, "classes_", None)
        if classes_attr is not None:
            return [str(c) for c in classes_attr][:n_columns]
        return [f"class_{i}" for i in range(int(n_columns))]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coerce_frame(data: Any) -> pd.DataFrame:
    if isinstance(data, pd.DataFrame):
        return data
    if isinstance(data, dict):
        return pd.DataFrame.from_records([data])
    arr = np.asarray(data)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    return pd.DataFrame(arr, columns=[f"f{i}" for i in range(arr.shape[1])])


def _to_probability_matrix(raw: Any) -> np.ndarray:
    arr = np.asarray(raw, dtype=float)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
        # Treat single-column 1D outputs as binary positive-class
        # probabilities; flesh out the complementary class for symmetry.
        complement = 1.0 - arr
        arr = np.concatenate([complement, arr], axis=1)
    return arr


def _to_score_matrix(raw: Any) -> np.ndarray:
    arr = np.asarray(raw, dtype=float)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    return arr


def _softmax(scores: np.ndarray) -> np.ndarray:
    if scores.shape[1] == 1:
        # Treat the 1-D column as a binary logit; emit [1-sigmoid, sigmoid].
        sig = 1.0 / (1.0 + np.exp(-scores))
        return np.concatenate([1.0 - sig, sig], axis=1)
    shifted = scores - np.max(scores, axis=1, keepdims=True)
    e = np.exp(shifted)
    return e / np.sum(e, axis=1, keepdims=True)


__all__ = ["ClassDistribution", "Classifier"]
