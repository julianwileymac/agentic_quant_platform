"""Forecasting baselines for the adhoc / notebook surface."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class QuickBaselineResult:
    backend: str
    horizon: int
    forecast: pd.Series
    metrics: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "horizon": self.horizon,
            "forecast": [
                {"timestamp": str(idx), "value": float(val)}
                for idx, val in self.forecast.items()
            ],
            "metrics": self.metrics,
            "metadata": self.metadata,
        }


def _coerce(series: pd.Series) -> pd.Series:
    s = pd.Series(series).dropna().astype(float)
    if s.empty:
        raise ValueError("Series has no usable values")
    if not isinstance(s.index, pd.DatetimeIndex):
        s.index = pd.to_datetime(s.index, errors="coerce")
        s = s[s.index.notna()]
    return s.sort_index()


def quick_naive_baseline(
    series: pd.Series,
    *,
    horizon: int = 20,
    strategy: str = "last",
) -> QuickBaselineResult:
    """Naive forecast baseline (last / mean / drift).

    Useful as a floor that any "real" model should beat. Runs entirely in
    NumPy and never raises on optional-dep absence.
    """
    s = _coerce(series)
    if strategy not in {"last", "mean", "drift"}:
        raise ValueError(f"Unknown strategy {strategy!r}")
    freq = pd.infer_freq(s.index) or "D"
    future_index = pd.date_range(
        start=s.index[-1] + pd.tseries.frequencies.to_offset(freq),
        periods=int(horizon),
        freq=freq,
    )
    if strategy == "last":
        values = np.repeat(float(s.iloc[-1]), int(horizon))
    elif strategy == "mean":
        values = np.repeat(float(s.mean()), int(horizon))
    else:  # drift
        diff = float(s.iloc[-1] - s.iloc[0]) / max(1, len(s) - 1)
        values = float(s.iloc[-1]) + diff * np.arange(1, int(horizon) + 1)
    return QuickBaselineResult(
        backend=f"naive_{strategy}",
        horizon=int(horizon),
        forecast=pd.Series(values, index=future_index, name="yhat"),
        metadata={"n_train": int(len(s))},
    )


def quick_theta(
    series: pd.Series,
    *,
    horizon: int = 20,
    sp: int | None = None,
    deseasonalize: bool = True,
) -> QuickBaselineResult:
    """Theta forecast via sktime."""
    try:
        from sktime.forecasting.theta import ThetaForecaster
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "sktime is not installed. Install the `ml-forecast` extra."
        ) from exc
    s = _coerce(series)
    forecaster = ThetaForecaster(
        sp=int(sp) if sp else None,
        deseasonalize=bool(deseasonalize),
    )
    forecaster.fit(s)
    pred = forecaster.predict(fh=list(range(1, int(horizon) + 1)))
    if not isinstance(pred, pd.Series):
        pred = pd.Series(pred)
    pred.name = "yhat"
    return QuickBaselineResult(
        backend="theta",
        horizon=int(horizon),
        forecast=pred,
        metadata={"n_train": int(len(s)), "sp": sp, "deseasonalize": deseasonalize},
    )


__all__ = [
    "QuickBaselineResult",
    "quick_naive_baseline",
    "quick_theta",
]
