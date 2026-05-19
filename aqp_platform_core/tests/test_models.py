"""Wire-format model smoke tests."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from aqp_platform_core.models import (
    AlertEvent,
    AlertSeverity,
    DeploymentLifecyclePhase,
    DeploymentSpec,
    DeploymentStatus,
    MetricPoint,
    ResourceLimits,
    ResponseEnvelope,
)


def test_deployment_spec_round_trips() -> None:
    spec = DeploymentSpec(
        service_id="aqp-api",
        image="ghcr.io/julianwiley/aqp-api:2026-05-18",
        replicas=3,
        env={"AQP_ENV": "prod"},
        ports=[8000, 8001],
        resources=ResourceLimits(cpu_request="500m", memory_request="1Gi"),
    )
    payload = spec.model_dump()
    rebuilt = DeploymentSpec.model_validate(payload)
    assert rebuilt == spec


def test_deployment_spec_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        DeploymentSpec(
            service_id="aqp-api",
            image="x:latest",
            unknown_field=True,  # type: ignore[call-arg]
        )


def test_deployment_status_defaults_to_unknown_phase() -> None:
    status = DeploymentStatus(service_id="x", provider="docker_compose")
    assert status.phase == DeploymentLifecyclePhase.UNKNOWN


def test_metric_point_requires_timestamp() -> None:
    point = MetricPoint(
        service_id="aqp-api",
        provider="kubernetes",
        metric="cpu_usage_pct",
        value=72.5,
        timestamp=datetime.now(timezone.utc),
    )
    assert point.value == pytest.approx(72.5)


def test_alert_event_severity_enum() -> None:
    event = AlertEvent(
        alert_id="alert-1",
        service_id="aqp-api",
        provider="kubernetes",
        severity=AlertSeverity.CRITICAL,
        title="High CPU",
        message="CPU > 85% for 60 s",
        timestamp=datetime.now(timezone.utc),
    )
    assert event.severity is AlertSeverity.CRITICAL


def test_response_envelope_generic_typing() -> None:
    envelope: ResponseEnvelope[DeploymentStatus] = ResponseEnvelope(
        status="ok",
        data=DeploymentStatus(service_id="aqp-api", provider="kubernetes"),
    )
    assert envelope.error is None
    assert envelope.data is not None
    assert envelope.data.service_id == "aqp-api"
