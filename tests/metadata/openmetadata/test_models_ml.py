"""Tests for OpenMetadata ML models."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from aqp.metadata.openmetadata import FeatureSource, MlFeature, MlHyperParameter, MlModel


def _valid_model_payload() -> dict[str, object]:
    """Return a valid baseline payload for `MlModel` tests."""
    return {
        "urn": "urn:aqp:mlmodel:dev:lstm_classifier_v3",
        "name": "LSTM Direction Classifier",
        "algorithm": "lstm_classifier",
        "ml_features": [
            MlFeature(
                name="rolling_zscore_20",
                data_type="numerical",
                feature_sources=[
                    FeatureSource(
                        source_urn="urn:aqp:dataset:dev:aqp_silver_alpha.daily_bars.close",
                        source_data_type="float64",
                    )
                ],
                feature_algorithm="rolling z-score(20)",
            )
        ],
        "ml_hyper_parameters": [
            MlHyperParameter(
                name="lookback",
                value="20",
                value_type="int",
                description="Number of lookback periods used for sequence windows.",
            )
        ],
        "target": "direction_label",
        "status": "Staging",
    }


def test_ml_model_valid_payload_and_schema_has_json_schema() -> None:
    """Valid ML payloads should parse and expose Draft-2020 schema metadata."""
    payload = _valid_model_payload()
    model = MlModel(**payload)

    assert model.urn == payload["urn"]
    assert model.algorithm == "lstm_classifier"
    schema = MlModel.model_json_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_ml_model_rejects_invalid_urn() -> None:
    """Model URN validation should reject non-AQP URNs."""
    payload = _valid_model_payload()
    payload["urn"] = "urn:foo:bar"

    with pytest.raises(ValidationError):
        MlModel(**payload)


def test_ml_model_requires_target() -> None:
    """`target` is required and should produce a field-level validation error."""
    payload = _valid_model_payload()
    payload.pop("target")

    with pytest.raises(ValidationError) as exc_info:
        MlModel(**payload)
    assert "target" in str(exc_info.value)


def test_ml_model_rejects_unknown_algorithm() -> None:
    """Algorithm names outside the resolved registry/fallback set should fail."""
    payload = _valid_model_payload()
    payload["algorithm"] = "definitely_not_real"

    with pytest.raises(ValidationError) as exc_info:
        MlModel(**payload)
    assert "algorithm" in str(exc_info.value)
