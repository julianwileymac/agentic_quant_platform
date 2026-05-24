"""Tests for the Phase 5 PredictorHub."""
from __future__ import annotations

import pytest

from aqp_models.predictors import (
    PredictorHub,
    PredictorSpec,
    list_predictors,
    register_predictor,
)


def test_predictor_spec_hash_is_stable():
    """Identical specs produce identical hashes."""
    spec_a = PredictorSpec(
        name="test",
        model_kind="xgboost",
        label_kind="regression",
        target_horizon="1d",
        feature_columns=["a", "b"],
        target_column="ret_1d",
    )
    spec_b = PredictorSpec(
        name="test",
        model_kind="xgboost",
        label_kind="regression",
        target_horizon="1d",
        feature_columns=["a", "b"],
        target_column="ret_1d",
    )
    assert spec_a.spec_hash() == spec_b.spec_hash()


def test_predictor_spec_hash_excludes_tenancy():
    """workspace_id / project_id do NOT participate in the hash.

    The same logical predictor used by different tenants produces
    the same hash so re-snapshotting is idempotent.
    """
    spec_a = PredictorSpec(
        name="test",
        model_kind="xgboost",
        label_kind="regression",
        target_horizon="1d",
        feature_columns=["a"],
        target_column="ret_1d",
        workspace_id="ws-1",
    )
    spec_b = PredictorSpec(
        name="test",
        model_kind="xgboost",
        label_kind="regression",
        target_horizon="1d",
        feature_columns=["a"],
        target_column="ret_1d",
        workspace_id="ws-2",
    )
    assert spec_a.spec_hash() == spec_b.spec_hash()


def test_predictor_spec_hash_changes_on_hyperparams():
    """Different hyperparams produce different hashes."""
    spec_a = PredictorSpec(
        name="test",
        model_kind="xgboost",
        label_kind="regression",
        target_horizon="1d",
        feature_columns=["a"],
        target_column="ret_1d",
        hyperparams={"max_depth": 6},
    )
    spec_b = PredictorSpec(
        name="test",
        model_kind="xgboost",
        label_kind="regression",
        target_horizon="1d",
        feature_columns=["a"],
        target_column="ret_1d",
        hyperparams={"max_depth": 8},
    )
    assert spec_a.spec_hash() != spec_b.spec_hash()


def test_hub_picks_correct_factory_for_xgb_regression():
    """The XGBoost regression factory is registered out of the box."""
    spec = PredictorSpec(
        name="xgb",
        model_kind="xgboost",
        label_kind="regression",
        target_horizon="1d",
        feature_columns=["a"],
        target_column="r",
    )
    hub = PredictorHub()
    factory = hub.factory_for(spec)
    assert callable(factory)


def test_hub_picks_correct_factory_for_lstm_classification():
    spec = PredictorSpec(
        name="lstm",
        model_kind="lstm",
        label_kind="classification",
        target_horizon="20d",
        feature_columns=["a"],
        target_column="dir",
        sequence_length=60,
        classes=["down", "up"],
    )
    hub = PredictorHub()
    factory = hub.factory_for(spec)
    assert callable(factory)


def test_hub_raises_for_unknown_combo():
    spec = PredictorSpec(
        name="unknown",
        model_kind="random_forest",  # not registered by default
        label_kind="ranking",
        target_horizon="1d",
        feature_columns=["a"],
        target_column="r",
    )
    hub = PredictorHub()
    with pytest.raises(KeyError):
        hub.factory_for(spec)


def test_list_predictors_returns_registry_entries():
    """list_predictors() lists every registered factory."""
    entries = list_predictors()
    assert len(entries) >= 4  # xgb/reg, xgb/cls, lstm/reg, lstm/cls
    kinds = {(e["model_kind"], e["label_kind"]) for e in entries}
    assert ("xgboost", "regression") in kinds
    assert ("lstm", "classification") in kinds


def test_register_predictor_decorator_adds_factory():
    """Adding a new factory makes it discoverable."""

    @register_predictor(model_kind="dummy", label_kind="regression")
    def _dummy_factory(spec: PredictorSpec):
        return {"kind": "dummy_model"}

    spec = PredictorSpec(
        name="dummy",
        model_kind="dummy",  # type: ignore[arg-type]
        label_kind="regression",
        target_horizon="1d",
        feature_columns=["a"],
        target_column="r",
    )
    hub = PredictorHub()
    model = hub.build(spec)
    assert model == {"kind": "dummy_model"}


def test_spec_canonical_body_is_json_friendly():
    """The canonical body has no non-JSON-serialisable values."""
    import json

    spec = PredictorSpec(
        name="test",
        model_kind="xgboost",
        label_kind="regression",
        target_horizon="1d",
        feature_columns=["a"],
        target_column="r",
        hyperparams={"max_depth": 6, "extra": [1, 2, 3]},
    )
    body = spec.canonical_body()
    # Round-trip via JSON
    s = json.dumps(body, sort_keys=True)
    assert "max_depth" in s
    assert "[1, 2, 3]" in s
