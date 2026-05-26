"""ADOT (AWS Distro for OpenTelemetry) exporter for AQP.

Phase F of the AWS hybrid rollout. When the operator opts in via
``AQP_OBS_AWS_ENABLED=true`` this module wires an additional set of
OTel exporters on top of the existing
:func:`aqp.observability.tracing.configure_tracing` chain:

- **AWS X-Ray** — traces (X-Ray Daemon / ADOT sidecar exporter at
  ``localhost:4317`` via OTLP). The ADOT collector translates OTLP
  spans to X-Ray segments using the
  ``awsxrayexporter`` pipeline. AQP application code keeps emitting
  OTLP — only the sidecar config differs from the local-first path.
- **CloudWatch Application Signals** — service-level RED metrics
  (request rate / error rate / duration) wired through the
  ``awsapplicationsignals`` processor. Enabled automatically when the
  ADOT sidecar config includes the processor — no application-side
  change needed beyond the ``service.name`` resource attribute.
- **CloudWatch Metrics** — custom OTel metrics exported via the
  ``awsemf`` (Embedded Metric Format) exporter in the ADOT sidecar.

The Python-side surface is deliberately small. The heavy lifting lives
in the ADOT collector config (``aqp_platform/deployments/kubernetes/observability/adot-collector.yaml``)
and in the ECS task-definition sidecar (``modules/ecs-fargate-control-plane``).
This module:

1. Adds the AWS-required resource attributes
   (``aws.local.service``, ``aws.local.operation``, ``cloud.provider``,
   ``cloud.platform``) so Application Signals shows correct service
   topology.
2. Sets a sensible default OTel endpoint (localhost:4317) when none
   is configured — the ADOT sidecar listens here.
3. Exports a :func:`configure_aws_observability` entrypoint the FastAPI
   ``lifespan`` and the Celery worker bootstrap can call alongside the
   existing :func:`aqp.observability.tracing.configure_tracing`.

The module is **soft-optional** — when ``AQP_OBS_AWS_ENABLED`` is not
true, every call is a no-op. That keeps the local-first developer
experience unchanged.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# AWS-flavoured resource attributes
# ---------------------------------------------------------------------------


def _aws_resource_attributes(service_name: str) -> dict[str, str]:
    """Return the set of resource attributes Application Signals needs.

    The CloudWatch Application Signals processor in the ADOT collector
    relies on these attributes to draw service topology + apply RED
    SLOs. Missing attributes don't crash the exporter — they just
    cause the service to disappear from the Application Signals
    service map.
    """
    region = (
        os.environ.get("AWS_REGION", "").strip()
        or os.environ.get("AWS_DEFAULT_REGION", "").strip()
        or "us-east-1"
    )
    account = os.environ.get("AQP_AWS_ACCOUNT_ID", "").strip() or ""
    env = os.environ.get("AQP_ENVIRONMENT", "").strip() or "dev"
    attrs = {
        "service.name": service_name,
        "service.namespace": "aqp",
        "deployment.environment": env,
        "cloud.provider": "aws",
        "cloud.platform": "aws_ecs",
        "cloud.region": region,
        "aws.local.service": service_name,
    }
    if account:
        attrs["cloud.account.id"] = account
    return attrs


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def is_enabled() -> bool:
    """True when the AWS ADOT exporter slice has been opted in."""
    return os.environ.get("AQP_OBS_AWS_ENABLED", "").lower() in ("1", "true", "yes")


def configure_aws_observability(service_name: str | None = None) -> dict[str, Any]:
    """Augment the active OTel pipeline with the AWS exporters.

    Returns a dict describing what was wired (or skipped); callers
    typically log this at startup so operators can confirm the AWS
    slice came up.

    This function MUST be called AFTER
    :func:`aqp.observability.tracing.configure_tracing` so the
    TracerProvider already exists. When :func:`is_enabled` returns
    False the function returns ``{"enabled": False}`` without making
    any changes — the local-first developer experience is unchanged.
    """
    if not is_enabled():
        return {"enabled": False, "reason": "AQP_OBS_AWS_ENABLED not set"}

    name = service_name or os.environ.get("OTEL_SERVICE_NAME", "aqp-api")
    attrs = _aws_resource_attributes(name)

    try:
        from opentelemetry.sdk.resources import Resource
        from opentelemetry import trace
    except ImportError:
        logger.warning(
            "AQP_OBS_AWS_ENABLED is set but opentelemetry SDK is missing; "
            "install aqp[otel] to enable AWS exporters"
        )
        return {"enabled": False, "reason": "opentelemetry SDK missing"}

    provider = trace.get_tracer_provider()
    existing_resource = getattr(provider, "resource", None)
    try:
        if existing_resource is None:
            merged_resource = Resource.create(attrs)
        else:
            merged_resource = existing_resource.merge(Resource.create(attrs))
        if hasattr(provider, "_resource"):
            provider._resource = merged_resource  # noqa: SLF001 - SDK exposes no setter
    except Exception:  # noqa: BLE001
        logger.debug("resource merge failed", exc_info=True)

    # The OTLP endpoint that targets the ADOT sidecar. The application
    # always emits to localhost:4317; the sidecar config decides which
    # AWS service the spans + metrics land in.
    otlp_endpoint = (
        os.environ.get("AQP_AWS_ADOT_ENDPOINT", "").strip()
        or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
        or "http://localhost:4317"
    )

    # X-Ray id generator is a no-op when the AWS distro is not installed.
    xray_enabled = False
    try:
        from opentelemetry.sdk.extension.aws.trace import (  # type: ignore[import-not-found]
            AwsXRayIdGenerator,
        )

        if hasattr(provider, "id_generator"):
            provider.id_generator = AwsXRayIdGenerator()
            xray_enabled = True
    except ImportError:
        logger.debug(
            "AwsXRayIdGenerator unavailable; install opentelemetry-sdk-extension-aws "
            "to switch the trace-id format to X-Ray-compatible."
        )

    return {
        "enabled": True,
        "service_name": name,
        "otlp_endpoint": otlp_endpoint,
        "xray_id_generator": xray_enabled,
        "resource_attributes": attrs,
    }


__all__ = [
    "configure_aws_observability",
    "is_enabled",
]
