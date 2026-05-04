"""Quick anomaly-detection helpers for notebooks (PyOD)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class QuickAnomalyResult:
    detector: str
    contamination: float
    n_rows: int
    n_features: int
    score_mean: float = 0.0
    score_std: float = 0.0
    score_p95: float = 0.0
    n_anomalies: int = 0
    anomaly_indices: list[int] = field(default_factory=list)
    scores: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict

        return asdict(self)


def _prepare(features: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    df = features.copy()
    if isinstance(df, pd.Series):
        df = df.to_frame()
    df = df.replace([np.inf, -np.inf], np.nan).dropna()
    return df.to_numpy(dtype=float), [str(c) for c in df.columns]


def _summarize(
    detector_name: str,
    detector: Any,
    X: np.ndarray,
    contamination: float,
    feature_names: list[str],
) -> QuickAnomalyResult:
    if X.size == 0:
        return QuickAnomalyResult(
            detector=detector_name,
            contamination=contamination,
            n_rows=0,
            n_features=len(feature_names),
        )
    detector.fit(X)
    if hasattr(detector, "decision_function"):
        scores = np.asarray(detector.decision_function(X), dtype=float)
    else:
        scores = np.asarray(detector.decision_scores_, dtype=float)[: len(X)]
    threshold = float(np.quantile(scores, 1.0 - contamination))
    anomaly_idx = np.where(scores > threshold)[0]
    return QuickAnomalyResult(
        detector=detector_name,
        contamination=contamination,
        n_rows=int(len(X)),
        n_features=int(X.shape[1]),
        score_mean=float(scores.mean()),
        score_std=float(scores.std()),
        score_p95=float(np.quantile(scores, 0.95)),
        n_anomalies=int(len(anomaly_idx)),
        anomaly_indices=anomaly_idx.tolist()[:1000],
        scores=scores.tolist()[:1000],
    )


def quick_iforest(
    features: pd.DataFrame,
    *,
    contamination: float = 0.05,
    n_estimators: int = 100,
) -> QuickAnomalyResult:
    """Run an Isolation Forest in two lines."""
    try:
        from pyod.models.iforest import IForest
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "pyod is not installed. Install the `ml-anomaly` extra."
        ) from exc
    X, feats = _prepare(features)
    detector = IForest(contamination=contamination, n_estimators=n_estimators)
    return _summarize("iforest", detector, X, contamination, feats)


def quick_ecod(
    features: pd.DataFrame, *, contamination: float = 0.05
) -> QuickAnomalyResult:
    """Run ECOD (empirical cumulative distribution outlier detection)."""
    try:
        from pyod.models.ecod import ECOD
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "pyod is not installed. Install the `ml-anomaly` extra."
        ) from exc
    X, feats = _prepare(features)
    return _summarize("ecod", ECOD(contamination=contamination), X, contamination, feats)


def quick_lof(
    features: pd.DataFrame,
    *,
    contamination: float = 0.05,
    n_neighbors: int = 20,
) -> QuickAnomalyResult:
    """Run LOF (Local Outlier Factor)."""
    try:
        from pyod.models.lof import LOF
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "pyod is not installed. Install the `ml-anomaly` extra."
        ) from exc
    X, feats = _prepare(features)
    return _summarize(
        "lof",
        LOF(contamination=contamination, n_neighbors=n_neighbors),
        X,
        contamination,
        feats,
    )


__all__ = [
    "QuickAnomalyResult",
    "quick_ecod",
    "quick_iforest",
    "quick_lof",
]
