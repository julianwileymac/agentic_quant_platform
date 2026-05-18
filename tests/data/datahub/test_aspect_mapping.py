"""Tests for DataHub aspect <-> AQP aspect mapping helpers."""
from __future__ import annotations

import pytest

from aqp.data.datahub import aspect_mapping


def test_aqp_urn_to_datahub_dataset_urn() -> None:
    """Dataset URNs map to DataHub dataset entity URNs."""
    datahub_urn = aspect_mapping.aqp_urn_to_datahub_entity_urn(
        "urn:aqp:dataset:prod:foo.bar"
    )
    assert datahub_urn == "urn:li:dataset:(urn:li:dataPlatform:aqp,foo.bar,PROD)"


def test_aqp_urn_to_datahub_mlmodel_urn() -> None:
    """ML model URNs map to DataHub mlModel entity URNs."""
    datahub_urn = aspect_mapping.aqp_urn_to_datahub_entity_urn(
        "urn:aqp:mlmodel:prod:lstm_v1"
    )
    assert datahub_urn == "urn:li:mlModel:(urn:li:dataPlatform:aqp,lstm_v1,PROD)"


def test_build_datahub_aspect_returns_none_when_sdk_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SDK import failures return None instead of raising."""
    monkeypatch.setattr(aspect_mapping, "_load_schema_classes", lambda: None)
    aspect = aspect_mapping.build_datahub_aspect(
        "mlModelMetadata",
        {"name": "lstm_v1", "description": "model"},
    )
    assert aspect is None


def test_build_datahub_aspect_ml_model_when_sdk_present() -> None:
    """When DataHub SDK is present we build the expected schema class."""
    pytest.importorskip("datahub.metadata.schema_classes")
    aspect = aspect_mapping.build_datahub_aspect(
        "mlModelMetadata",
        {
            "name": "lstm_v1",
            "description": "Model metadata from AQP",
            "model_version": "v1",
        },
    )
    assert aspect is not None
    assert aspect.__class__.__name__ == "MLModelPropertiesClass"
