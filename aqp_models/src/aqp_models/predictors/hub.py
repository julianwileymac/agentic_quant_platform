"""PredictorHub -- factory + registry for ML predictors.

Maps a :class:`PredictorSpec` to a concrete model factory and runs a
single training pass. Supports the two report-mandated cases:

* **XGBoost regression** -- ``model_kind='xgboost'``, ``label_kind='regression'``
* **LSTM classification** -- ``model_kind='lstm'``, ``label_kind='classification'``

The hub stays thin -- the heavy lifting is delegated to the existing
:mod:`aqp_models.models` factories which already wrap XGBoost / sklearn /
PyTorch / Keras / HuggingFace via the ``class`` / ``module_path`` /
``kwargs`` pattern.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from aqp_models.predictors.spec import PredictorSpec

logger = logging.getLogger(__name__)


# Registry: {(model_kind, label_kind): factory_fn}
_FACTORIES: dict[tuple[str, str], Callable[[PredictorSpec], Any]] = {}


def register_predictor(
    *, model_kind: str, label_kind: str
) -> Callable[[Callable[[PredictorSpec], Any]], Callable[[PredictorSpec], Any]]:
    """Decorator registering a factory for ``(model_kind, label_kind)``."""

    def _wrap(fn: Callable[[PredictorSpec], Any]) -> Callable[[PredictorSpec], Any]:
        key = (model_kind, label_kind)
        existing = _FACTORIES.get(key)
        if existing is not None and existing is not fn:
            logger.debug("Replacing predictor factory for %s", key)
        _FACTORIES[key] = fn
        return fn

    return _wrap


def list_predictors() -> list[dict[str, Any]]:
    """List every registered factory."""
    return [
        {"model_kind": k[0], "label_kind": k[1], "factory": fn.__name__}
        for k, fn in sorted(_FACTORIES.items())
    ]


@dataclass
class PredictorHub:
    """Dispatcher that picks the right factory for a spec.

    Used by the Phase 5 ML test endpoints, the bot runtime, and the
    Celery training tasks. Heavy lifting lives in the underlying
    factories; the hub is the routing layer.
    """

    def factory_for(self, spec: PredictorSpec) -> Callable[[PredictorSpec], Any]:
        key = (spec.model_kind, spec.label_kind)
        factory = _FACTORIES.get(key)
        if factory is None:
            raise KeyError(
                f"no predictor factory registered for {key!r} -- known: "
                f"{sorted(_FACTORIES)}"
            )
        return factory

    def build(self, spec: PredictorSpec) -> Any:
        """Instantiate the model object described by ``spec``."""
        return self.factory_for(spec)(spec)


# ---------------------------------------------------------------------------
# Default factories -- the two report-mandated cases
# ---------------------------------------------------------------------------


@register_predictor(model_kind="xgboost", label_kind="regression")
def _xgb_regression_factory(spec: PredictorSpec) -> Any:
    """XGBoost regression factory.

    Delegates to :mod:`aqp_models.models.tree` for the underlying XGBoost
    object (already a sanctioned registry entry). The hub adds the
    spec-aware hyperparam mapping.
    """
    try:
        from aqp_models.models.tree import XGBModel
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"XGBModel unavailable: {exc}") from exc

    hp = dict(spec.hyperparams)
    hp.setdefault("max_depth", 6)
    hp.setdefault("learning_rate", 0.05)
    hp.setdefault("n_estimators", 500)
    hp.setdefault("objective", "reg:squarederror")
    return XGBModel(**hp)


@register_predictor(model_kind="xgboost", label_kind="classification")
def _xgb_classification_factory(spec: PredictorSpec) -> Any:
    """XGBoost classification factory."""
    try:
        from aqp_models.models.tree import XGBModel
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"XGBModel unavailable: {exc}") from exc

    hp = dict(spec.hyperparams)
    hp.setdefault("max_depth", 5)
    hp.setdefault("learning_rate", 0.05)
    hp.setdefault("n_estimators", 500)
    hp.setdefault("objective", "multi:softprob" if (spec.classes and len(spec.classes) > 2) else "binary:logistic")
    return XGBModel(**hp)


@register_predictor(model_kind="lstm", label_kind="classification")
def _lstm_classification_factory(spec: PredictorSpec) -> Any:
    """PyTorch LSTM classification factory.

    The report explicitly calls out LSTMs as the strongest medium-horizon
    (7-30 day) directional classifier. We default to the
    :class:`aqp_models.models.torch.lstm.LSTMModel` shape and override the
    head for classification.
    """
    try:
        from aqp_models.models.torch.lstm import LSTMModel
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"LSTMModel unavailable: {exc}") from exc

    hp = dict(spec.hyperparams)
    hp.setdefault("hidden_size", 64)
    hp.setdefault("num_layers", 2)
    hp.setdefault("dropout", 0.2)
    hp.setdefault("sequence_length", spec.sequence_length or 60)
    hp.setdefault("task_kind", "classification")
    if spec.classes:
        hp.setdefault("num_classes", len(spec.classes))
    return LSTMModel(**hp)


@register_predictor(model_kind="lstm", label_kind="regression")
def _lstm_regression_factory(spec: PredictorSpec) -> Any:
    """PyTorch LSTM regression factory (less common)."""
    try:
        from aqp_models.models.torch.lstm import LSTMModel
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"LSTMModel unavailable: {exc}") from exc

    hp = dict(spec.hyperparams)
    hp.setdefault("hidden_size", 64)
    hp.setdefault("num_layers", 2)
    hp.setdefault("dropout", 0.2)
    hp.setdefault("sequence_length", spec.sequence_length or 60)
    hp.setdefault("task_kind", "regression")
    return LSTMModel(**hp)


__all__ = [
    "PredictorHub",
    "list_predictors",
    "register_predictor",
]
