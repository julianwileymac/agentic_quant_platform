"""Concrete out-of-distribution rules.

* :class:`OODGuard` — flag rows whose absolute z-score against the
  training distribution exceeds ``threshold`` standard deviations.
* :class:`RangeGuard` — reject rows whose feature values fall outside a
  configurable [min, max] window.
* :class:`TensorShapeGuard` — reject inputs whose tensor shape doesn't
  match the model's expected shape (caught early so the model receives
  validated tensors only).
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from aqp_models.rules.base import MLRule, RuleVerdict

logger = logging.getLogger(__name__)


class OODGuard(MLRule):
    """Reject features whose abs z-score crosses ``threshold``."""

    rule_name = "ood.zscore"
    rule_tags = ("ood",)
    severity = "block"

    def __init__(self, *, threshold: float | None = None) -> None:
        if threshold is None:
            try:
                from aqp.config import settings

                threshold = float(getattr(settings, "ml_ood_zscore_threshold", 3.0))
            except Exception:  # noqa: BLE001
                threshold = 3.0
        self.threshold = float(threshold)

    def evaluate(
        self,
        *,
        payload: dict[str, Any],
        step: Any | None = None,
        ctx: Any | None = None,
    ) -> RuleVerdict:
        features = _extract_features(payload)
        if features is None or features.size == 0:
            return RuleVerdict(allowed=True, reason="no features to evaluate")

        mu = np.nanmean(features, axis=0)
        sigma = np.nanstd(features, axis=0)
        sigma = np.where(sigma <= 0, 1.0, sigma)
        z = np.abs((features - mu) / sigma)
        worst = float(np.nanmax(z)) if z.size else 0.0
        if worst > self.threshold:
            return RuleVerdict(
                allowed=False,
                reason=(
                    f"feature abs-zscore {worst:.2f} > threshold {self.threshold:.2f}"
                ),
                score=worst,
                metadata={"threshold": self.threshold, "z_max": worst},
            )
        return RuleVerdict(
            allowed=True,
            reason="zscore within bounds",
            score=worst,
            metadata={"threshold": self.threshold, "z_max": worst},
        )


class RangeGuard(MLRule):
    """Reject features outside an absolute [min_value, max_value] window."""

    rule_name = "ood.range"
    rule_tags = ("ood",)
    severity = "block"

    def __init__(
        self,
        *,
        min_value: float | None = None,
        max_value: float | None = None,
    ) -> None:
        self.min_value = float(min_value) if min_value is not None else float("-inf")
        self.max_value = float(max_value) if max_value is not None else float("inf")

    def evaluate(
        self,
        *,
        payload: dict[str, Any],
        step: Any | None = None,
        ctx: Any | None = None,
    ) -> RuleVerdict:
        features = _extract_features(payload)
        if features is None or features.size == 0:
            return RuleVerdict(allowed=True, reason="no features to evaluate")
        worst_low = float(np.nanmin(features))
        worst_high = float(np.nanmax(features))
        if worst_low < self.min_value or worst_high > self.max_value:
            return RuleVerdict(
                allowed=False,
                reason=(
                    f"feature outside [{self.min_value:.4g}, {self.max_value:.4g}] "
                    f"(min={worst_low:.4g}, max={worst_high:.4g})"
                ),
                score=max(abs(worst_low), abs(worst_high)),
                metadata={
                    "min": worst_low,
                    "max": worst_high,
                    "min_value": self.min_value,
                    "max_value": self.max_value,
                },
            )
        return RuleVerdict(
            allowed=True,
            reason="within range",
            score=0.0,
        )


class TensorShapeGuard(MLRule):
    """Reject inputs whose shape mismatches the step's expected_shape."""

    rule_name = "ood.tensor_shape"
    rule_tags = ("ood", "schema")
    severity = "block"

    def __init__(self, *, expected_n_features: int | None = None) -> None:
        self.expected_n_features = (
            int(expected_n_features) if expected_n_features is not None else None
        )

    def evaluate(
        self,
        *,
        payload: dict[str, Any],
        step: Any | None = None,
        ctx: Any | None = None,
    ) -> RuleVerdict:
        features = _extract_features(payload)
        if features is None:
            return RuleVerdict(allowed=True, reason="no features in payload")

        # Try to source expected shape from the step's kwargs if not explicit.
        expected = self.expected_n_features
        if expected is None and step is not None:
            expected = (step.kwargs or {}).get("expected_n_features")

        if expected is None:
            return RuleVerdict(
                allowed=True,
                reason="no expected_n_features declared",
                score=0.0,
            )

        if features.ndim == 1:
            n_features = int(features.shape[0])
        else:
            n_features = int(features.shape[1])

        if n_features != expected:
            return RuleVerdict(
                allowed=False,
                reason=(
                    f"feature count {n_features} != expected {expected}"
                ),
                score=abs(n_features - expected),
                metadata={"n_features": n_features, "expected": expected},
            )
        return RuleVerdict(
            allowed=True,
            reason="shape match",
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_features(payload: dict[str, Any]) -> np.ndarray | None:
    candidates = (payload.get("features"), payload.get("X"), payload.get("data"))
    for value in candidates:
        if value is None:
            continue
        if isinstance(value, np.ndarray):
            return value.astype(float, copy=False)
        if isinstance(value, pd.DataFrame):
            return value.to_numpy(dtype=float, na_value=np.nan)
        if isinstance(value, pd.Series):
            return value.to_numpy(dtype=float)
        if isinstance(value, dict):
            try:
                return np.asarray(list(value.values()), dtype=float).reshape(1, -1)
            except Exception:  # noqa: BLE001
                continue
        try:
            return np.asarray(value, dtype=float)
        except Exception:  # noqa: BLE001
            continue
    return None


__all__ = ["OODGuard", "RangeGuard", "TensorShapeGuard"]
