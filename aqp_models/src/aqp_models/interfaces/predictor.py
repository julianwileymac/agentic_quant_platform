"""Predictor — point-in-time value estimation.

The report's first reference application: estimate a scalar (or vector)
value from a feature tensor at a single instant. Backed by any AQP
:class:`aqp_models.base.Model` that returns numeric scores.

Typical agent usage::

    predictor = Predictor(model=lgb_returns_1d, alias="lgb_returns_1d")
    result = predictor.predict(feature_row)
    # result.values: np.ndarray, result.metadata.elapsed_ms: 3.2
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
class PredictionResult:
    """Structured output of :meth:`Predictor.predict`."""

    values: np.ndarray
    feature_names: list[str] = field(default_factory=list)
    metadata: InterfaceMetadata | None = None

    def to_json(self) -> dict[str, Any]:
        arr = np.asarray(self.values, dtype=float)
        return {
            "values": arr.reshape(-1).tolist(),
            "shape": list(arr.shape),
            "feature_names": list(self.feature_names),
            "metadata": self.metadata.to_json() if self.metadata else None,
        }


@register("Predictor", kind="interface")
class Predictor(PolymorphicInterface):
    """Polymorphic wrapper for point-in-time value estimators.

    The wrapper accepts the same input shapes the underlying model
    accepts:

    - ``pandas.DataFrame`` (panel-shaped, multi-index) — passed through
      to ``Model.predict`` unchanged.
    - ``numpy.ndarray`` — coerced to a single-row DataFrame.
    - ``dict[str, float]`` — coerced via :func:`pandas.DataFrame.from_records`.

    Output is always normalised to a :class:`PredictionResult` so agents
    can reason about shape / metadata without sniffing the underlying
    framework.
    """

    interface_kind = "predictor"
    alias = "predictor"

    def predict(self, features: Any, **kwargs: Any) -> PredictionResult:
        started = datetime.utcnow()
        frame, names = _coerce_features(features)
        raw = self._delegate_predict(frame, **kwargs)
        values = _coerce_values(raw)
        return PredictionResult(
            values=values,
            feature_names=names,
            metadata=self._build_metadata(
                started=started,
                extras={"n_rows": int(values.shape[0])},
            ),
        )

    def supports(self, model: Any) -> bool:
        return hasattr(model, "predict") or callable(model)


# ---------------------------------------------------------------------------
# Coercion helpers — accept the three shapes agents send, normalise to a
# DataFrame and a numpy array.
# ---------------------------------------------------------------------------


def _coerce_features(features: Any) -> tuple[pd.DataFrame, list[str]]:
    if isinstance(features, pd.DataFrame):
        names = [str(c) for c in features.columns]
        return features, names
    if isinstance(features, dict):
        frame = pd.DataFrame.from_records([features])
        return frame, [str(c) for c in frame.columns]
    arr = np.asarray(features)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    names = [f"f{i}" for i in range(int(arr.shape[1]))]
    frame = pd.DataFrame(arr, columns=names)
    return frame, names


def _coerce_values(raw: Any) -> np.ndarray:
    if isinstance(raw, np.ndarray):
        return raw.astype(float, copy=False)
    if isinstance(raw, pd.Series):
        return raw.to_numpy(dtype=float)
    if isinstance(raw, pd.DataFrame):
        return raw.to_numpy(dtype=float)
    return np.asarray(raw, dtype=float)


__all__ = ["PredictionResult", "Predictor"]
