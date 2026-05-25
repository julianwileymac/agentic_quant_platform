"""Forecaster — multi-step temporal projection.

The report's second reference application. Used for yield-curve / vol
projection / multi-bar return forecasts where the agent needs an
H-step-ahead trajectory rather than a single-bar value.

Backed by either:

- a sequential :class:`aqp_models.base.Model` that accepts a history
  ``DataFrame`` and a ``horizon`` kwarg (sktime / Prophet / TCN
  forecasters), or
- a point-predictor wrapped in a recursive rollout (we step the
  predictor ``horizon`` times, feeding each step's output back in as
  the next-step's input).
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
class ForecastResult:
    """Structured output of :meth:`Forecaster.forecast`."""

    horizon: int
    values: np.ndarray
    index: list[Any] = field(default_factory=list)
    metadata: InterfaceMetadata | None = None

    def to_json(self) -> dict[str, Any]:
        arr = np.asarray(self.values, dtype=float)
        return {
            "horizon": int(self.horizon),
            "values": arr.reshape(-1).tolist(),
            "shape": list(arr.shape),
            "index": [str(i) for i in self.index],
            "metadata": self.metadata.to_json() if self.metadata else None,
        }


@register("Forecaster", kind="interface")
class Forecaster(PolymorphicInterface):
    """Polymorphic wrapper for multi-step forecasters.

    Two delegation paths:

    1. **Native forecaster** — when the underlying model exposes
       ``forecast(history, horizon)`` or ``predict(history,
       horizon=...)``, we call it directly.
    2. **Recursive rollout** — when only ``predict`` is available we
       step ``horizon`` times, treating the previous step's scalar /
       vector output as the most-recent feature row of the next call.

    The recursive path is intentionally conservative: it never reaches
    inside the model. Agents that need richer roll-outs (e.g. ensemble
    sampling) should call the underlying model directly via the
    :class:`aqp_models.handlers.ServeHandler`.
    """

    interface_kind = "forecaster"
    alias = "forecaster"

    def forecast(
        self,
        history: pd.DataFrame | np.ndarray,
        *,
        horizon: int,
        **kwargs: Any,
    ) -> ForecastResult:
        if horizon <= 0:
            raise ValueError("horizon must be >= 1")
        started = datetime.utcnow()
        frame = _coerce_history(history)
        idx_in = list(frame.index)

        # Native forecaster path
        if hasattr(self.model, "forecast"):
            raw = self.model.forecast(frame, horizon=horizon, **kwargs)
            values = _coerce_forecast(raw)
        elif _accepts_horizon_kwarg(self.model):
            raw = self.model.predict(frame, horizon=horizon, **kwargs)
            values = _coerce_forecast(raw)
        else:
            values = _recursive_rollout(self.model, frame, horizon=horizon)

        index = _build_forecast_index(idx_in, horizon)
        return ForecastResult(
            horizon=horizon,
            values=values,
            index=index,
            metadata=self._build_metadata(
                started=started,
                extras={"strategy": _strategy_used(self.model), "horizon": horizon},
            ),
        )

    def supports(self, model: Any) -> bool:
        return (
            hasattr(model, "forecast")
            or _accepts_horizon_kwarg(model)
            or hasattr(model, "predict")
        )


# ---------------------------------------------------------------------------
# Coercion + strategy detection
# ---------------------------------------------------------------------------


def _coerce_history(history: Any) -> pd.DataFrame:
    if isinstance(history, pd.DataFrame):
        return history
    arr = np.asarray(history)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    return pd.DataFrame(arr, columns=[f"f{i}" for i in range(arr.shape[1])])


def _coerce_forecast(raw: Any) -> np.ndarray:
    if isinstance(raw, pd.DataFrame):
        return raw.to_numpy(dtype=float)
    if isinstance(raw, pd.Series):
        return raw.to_numpy(dtype=float)
    return np.asarray(raw, dtype=float)


def _accepts_horizon_kwarg(model: Any) -> bool:
    predict = getattr(model, "predict", None)
    if predict is None:
        return False
    try:
        import inspect

        sig = inspect.signature(predict)
        return "horizon" in sig.parameters
    except (TypeError, ValueError):
        return False


def _strategy_used(model: Any) -> str:
    if hasattr(model, "forecast"):
        return "native_forecast"
    if _accepts_horizon_kwarg(model):
        return "predict_with_horizon"
    return "recursive_rollout"


def _build_forecast_index(history_index: list[Any], horizon: int) -> list[Any]:
    """Return a forward-walked index when history was DateTime-indexed."""
    if not history_index:
        return [f"t+{i+1}" for i in range(horizon)]
    last = history_index[-1]
    if isinstance(last, pd.Timestamp):
        # Best-effort daily step — agents that want intraday should pass
        # an explicit ``freq`` kwarg the native forecaster honours.
        return [last + pd.Timedelta(days=i + 1) for i in range(horizon)]
    return [f"t+{i+1}" for i in range(horizon)]


def _recursive_rollout(
    model: Any, history: pd.DataFrame, *, horizon: int
) -> np.ndarray:
    """Step the point-predictor ``horizon`` times.

    The rollout assumes the model is monotonic in its most-recent row —
    we treat the last row as the seed and overwrite a single ``y_hat``
    column at each step. Models that need a richer state should expose
    ``forecast`` natively.
    """
    rolling = history.copy()
    out: list[float] = []
    for _ in range(horizon):
        scalar = np.asarray(model.predict(rolling), dtype=float).reshape(-1)
        next_val = float(scalar[-1]) if scalar.size else 0.0
        out.append(next_val)
        new_row = rolling.iloc[[-1]].copy()
        # Heuristic: bump the first column by the predicted delta so the
        # next call sees a slightly different state. This is the
        # deterministic stand-in agents expect — when they need
        # richer dynamics they should switch to a real forecaster.
        if rolling.shape[1] > 0:
            new_row.iloc[0, 0] = next_val
        rolling = pd.concat([rolling, new_row], ignore_index=True)
    return np.asarray(out, dtype=float)


__all__ = ["ForecastResult", "Forecaster"]
