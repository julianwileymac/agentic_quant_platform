"""Tests for OpenMetadata pipeline models."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from aqp.metadata.openmetadata import Pipeline, PipelineTask


def _valid_pipeline_payload() -> dict[str, object]:
    """Return a valid payload for `Pipeline` tests."""
    return {
        "urn": "urn:aqp:pipeline:dev:nightly_alpha_research",
        "name": "Nightly Alpha Research",
        "pipeline_location": "dagster://job/nightly_alpha_research",
        "tasks": [
            PipelineTask(
                name="ingest_alpha_vantage",
                task_type="airbyte",
                description="Ingests nightly market data from Alpha Vantage.",
            ),
            PipelineTask(
                name="materialize_features",
                task_type="materialize",
                upstream_tasks=["ingest_alpha_vantage"],
            ),
        ],
        "start_date": datetime(2026, 5, 17, 0, 0, tzinfo=timezone.utc),
    }


def test_pipeline_valid_payload() -> None:
    """Valid pipeline payloads should parse and keep task DAG structure."""
    pipeline = Pipeline(**_valid_pipeline_payload())

    assert pipeline.urn.startswith("urn:aqp:pipeline:")
    assert [task.name for task in pipeline.tasks] == [
        "ingest_alpha_vantage",
        "materialize_features",
    ]


def test_pipeline_rejects_invalid_urn() -> None:
    """Pipeline URN must match canonical AQP URN format."""
    payload = _valid_pipeline_payload()
    payload["urn"] = "urn:foo:bar"

    with pytest.raises(ValidationError):
        Pipeline(**payload)


def test_pipeline_task_rejects_invalid_task_type() -> None:
    """Task type validation should enforce canonical lineage transform kinds."""
    with pytest.raises(ValidationError) as exc_info:
        PipelineTask(name="bad_task", task_type="totally_unknown")
    assert "task_type" in str(exc_info.value)
