"""Smoke tests for the new model wrappers added in the ML expansion.

These verify the wrappers register correctly and surface a clear
RuntimeError when the optional extra is absent. Real estimator paths
are exercised in framework-specific suites.
"""
from __future__ import annotations

import importlib

import pytest


def _import_or_skip(module_path: str):
    try:
        return importlib.import_module(module_path)
    except Exception as exc:
        pytest.skip(f"optional dep missing for {module_path}: {exc}")
    return None


def test_new_forecasting_wrappers_registered() -> None:
    """All new forecasting wrappers register with @register("Name")."""
    _import_or_skip("aqp.ml.models.forecasting")
    from aqp.core.registry import resolve

    for name in (
        "AutoETSForecastModel",
        "AutoARIMAForecastModel",
        "ThetaForecastModel",
        "BatsTbatsForecastModel",
    ):
        cls = resolve(name)
        assert cls is not None, f"{name} not registered"


def test_new_keras_wrappers_registered() -> None:
    _import_or_skip("aqp.ml.models.keras")
    from aqp.core.registry import resolve

    for name in ("KerasFunctionalModel", "KerasTabTransformerModel"):
        cls = resolve(name)
        assert cls is not None, f"{name} not registered"


def test_new_huggingface_wrappers_registered() -> None:
    _import_or_skip("aqp.ml.models.huggingface")
    from aqp.core.registry import resolve

    for name in (
        "HuggingFaceFinBertSentimentModel",
        "HuggingFaceTimeSeriesModel",
        "HuggingFaceGenerativeForecastModel",
    ):
        cls = resolve(name)
        assert cls is not None, f"{name} not registered"


def test_new_sklearn_wrappers_registered() -> None:
    _import_or_skip("aqp.ml.models.sklearn")
    from aqp.core.registry import resolve

    for name in ("SklearnStackingModel", "SklearnAutoPipelineModel"):
        cls = resolve(name)
        assert cls is not None, f"{name} not registered"


def test_tf_estimator_disabled_by_default(monkeypatch) -> None:
    """When AQP_TF_NATIVE_ENABLED is false, instantiation raises."""
    _import_or_skip("aqp.ml.models.tensorflow")
    from aqp.config import settings
    from aqp.ml.models.tensorflow import TFEstimatorModel

    monkeypatch.setattr(settings, "tf_native_enabled", False, raising=False)
    with pytest.raises(RuntimeError, match="disabled"):
        TFEstimatorModel(estimator="dnn")


def test_tf_estimator_unknown_kind(monkeypatch) -> None:
    _import_or_skip("aqp.ml.models.tensorflow")
    from aqp.config import settings
    from aqp.ml.models.tensorflow import TFEstimatorModel

    monkeypatch.setattr(settings, "tf_native_enabled", True, raising=False)
    with pytest.raises(ValueError):
        TFEstimatorModel(estimator="not-a-real-kind")


def test_huggingface_timeseries_gated(monkeypatch) -> None:
    _import_or_skip("aqp.ml.models.huggingface")
    from aqp.config import settings
    from aqp.ml.models.huggingface import HuggingFaceTimeSeriesModel

    monkeypatch.setattr(settings, "hf_timeseries_enabled", False, raising=False)
    with pytest.raises(RuntimeError):
        HuggingFaceTimeSeriesModel()


def test_pyod_anomaly_unknown_detector() -> None:
    from aqp.ml.models.anomaly import PyODAnomalyModel

    model = PyODAnomalyModel(detector="totally-fake")
    with pytest.raises(ValueError):
        model._make_detector()
