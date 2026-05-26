"""``moto``-backed tests for ``AwsProvider`` mutating ops (Phase B).

Exercises the surface lit up by Phase B of the AWS hybrid rollout:
``scale``, ``stop``, ``restart``, ``apply_config``, and ``rotate_secret``.
Each test skips when ``moto`` is not installed so a developer without
the cloud extras still gets a green pytest run.

Per AGENTS rule 26 + the management-engine credential-safety rule we
never read a real AWS account — moto stubs ECS / SSM / Secrets Manager
in-memory.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json

import pytest


def _has(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


pytestmark = pytest.mark.skipif(
    not _has("moto") or not _has("boto3"),
    reason="moto + boto3 required for AwsProvider mutating tests",
)


@pytest.fixture(autouse=True)
def _aws_env(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "test")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "test")


def _make_provider():
    from aqp_cp.providers.aws import AwsProvider

    return AwsProvider()


def test_scale_calls_update_service_with_desired_count():
    from moto import mock_aws

    with mock_aws():
        import boto3
        from aqp_platform_core.models.config import ConfigMapPatch

        client = boto3.client("ecs", region_name="us-east-1")
        client.create_cluster(clusterName="aqp-test")
        client.register_task_definition(
            family="aqp-admin",
            containerDefinitions=[{
                "name": "aqp-admin",
                "image": "placeholder:latest",
                "essential": True,
            }],
        )
        client.create_service(
            cluster="aqp-test",
            serviceName="aqp-admin",
            taskDefinition="aqp-admin",
            desiredCount=1,
            launchType="FARGATE",
            networkConfiguration={
                "awsvpcConfiguration": {
                    "subnets": ["subnet-1234"],
                    "assignPublicIp": "DISABLED",
                }
            },
        )

        provider = _make_provider()
        status = asyncio.run(provider.scale("aqp-admin", 3, namespace="aqp-test"))
        assert status.replicas_desired == 3

        # restart -> force_new_deployment=True (moto records the call).
        status_r = asyncio.run(provider.restart("aqp-admin", namespace="aqp-test"))
        assert status_r.service_id == "aqp-admin"


def test_apply_config_rejects_secret_like_keys():
    from moto import mock_aws

    with mock_aws():
        from aqp_platform_core.models.config import ConfigMapPatch
        from aqp_platform_core.providers.protocol import InfrastructureProviderError

        provider = _make_provider()
        patch = ConfigMapPatch(
            service_id="aqp-admin",
            values={"DB_PASSWORD": "leaks-secret"},
        )
        with pytest.raises(InfrastructureProviderError) as exc:
            asyncio.run(provider.apply_config(patch))
        assert exc.value.code == "secret_like_key"


def test_apply_config_writes_ssm_for_safe_keys(monkeypatch):
    from moto import mock_aws

    with mock_aws():
        import boto3
        from aqp_platform_core.models.config import ConfigMapPatch

        monkeypatch.setenv("AQP_ENVIRONMENT", "dev")
        provider = _make_provider()
        patch = ConfigMapPatch(
            service_id="aqp-admin",
            values={"LOG_LEVEL": "info", "FEATURE_X": "true"},
        )
        ok = asyncio.run(provider.apply_config(patch))
        assert ok is True

        ssm = boto3.client("ssm", region_name="us-east-1")
        params = ssm.get_parameters_by_path(
            Path="/aqp/dev/services/aqp-admin/",
            Recursive=True,
        )
        names = {p["Name"] for p in params.get("Parameters", [])}
        assert any(n.endswith("LOG_LEVEL") for n in names)
        assert any(n.endswith("FEATURE_X") for n in names)


def test_rotate_secret_rejects_out_of_prefix_secrets():
    from moto import mock_aws

    with mock_aws():
        from aqp_platform_core.providers.protocol import InfrastructureProviderError

        provider = _make_provider()
        with pytest.raises(InfrastructureProviderError) as exc:
            asyncio.run(
                provider.rotate_secret(
                    "aqp-admin",
                    secret_name="stripe/secret-not-ours",
                )
            )
        assert exc.value.code == "secret_outside_prefix"


def test_health_probe_returns_metadata_under_moto():
    from moto import mock_aws

    with mock_aws():
        provider = _make_provider()
        health = asyncio.run(provider.health())
        assert health.available is True
        assert health.metadata["region"] == "us-east-1"
