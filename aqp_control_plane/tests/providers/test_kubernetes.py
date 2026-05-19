"""kubernetes provider — unit tests over the parsing + translation helpers."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from aqp_cp.providers.kubernetes import (
    KubernetesProvider,
    _deployment_to_status,
    _parse_quantity_cpu,
    _parse_quantity_memory,
    _spec_to_deployment,
)
from aqp_platform_core.models.deployment import (
    DeploymentLifecyclePhase,
    DeploymentSpec,
    ResourceLimits,
)


class TestParseQuantity:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("500m", 0.5),
            ("2", 2.0),
            ("100n", 0.0000001),
            ("250u", 0.00025),
            ("", 0.0),
        ],
    )
    def test_cpu(self, value: str, expected: float) -> None:
        assert _parse_quantity_cpu(value) == pytest.approx(expected, rel=1e-6)

    @pytest.mark.parametrize(
        "value,expected_bytes",
        [
            ("512Ki", 512 * 1024),
            ("1Gi", 1024**3),
            ("256Mi", 256 * 1024**2),
            ("1000", 1000.0),
            ("1G", 1_000_000_000),
        ],
    )
    def test_memory(self, value: str, expected_bytes: float) -> None:
        assert _parse_quantity_memory(value) == pytest.approx(expected_bytes)


class TestSpecToDeployment:
    def test_basic_spec_includes_required_keys(self) -> None:
        spec = DeploymentSpec(
            service_id="aqp-api",
            image="ghcr.io/x:dev",
            replicas=3,
            namespace="aqp",
            env={"AQP_ENV": "prod"},
            ports=[8000],
            health_check_path="/healthz",
            health_check_port=8000,
            resources=ResourceLimits(
                cpu_request="500m", memory_request="1Gi", cpu_limit="1", memory_limit="2Gi"
            ),
            labels={"tier": "api"},
        )
        doc = _spec_to_deployment(spec, namespace="aqp")
        assert doc["kind"] == "Deployment"
        assert doc["metadata"]["name"] == "aqp-api"
        assert doc["metadata"]["namespace"] == "aqp"
        assert doc["spec"]["replicas"] == 3
        container = doc["spec"]["template"]["spec"]["containers"][0]
        assert container["image"] == "ghcr.io/x:dev"
        assert {"name": "AQP_ENV", "value": "prod"} in container["env"]
        assert container["resources"]["requests"]["cpu"] == "500m"
        assert container["resources"]["limits"]["memory"] == "2Gi"
        assert container["readinessProbe"]["httpGet"]["path"] == "/healthz"
        # Security context applied at pod level.
        assert (
            doc["spec"]["template"]["spec"]["securityContext"]["runAsNonRoot"] is True
        )

    def test_env_from_secrets_emits_envfrom(self) -> None:
        spec = DeploymentSpec(
            service_id="aqp-api",
            image="x",
            env_from_secrets=["aqp-secrets", "external-creds"],
        )
        doc = _spec_to_deployment(spec, namespace="default")
        container = doc["spec"]["template"]["spec"]["containers"][0]
        env_from = container.get("envFrom", [])
        secret_names = [e["secretRef"]["name"] for e in env_from]
        assert "aqp-secrets" in secret_names
        assert "external-creds" in secret_names


class TestDeploymentToStatus:
    def _mock_deployment(
        self, *, replicas: int, ready: int, name: str = "aqp-api", image: str = "x:1"
    ):
        return SimpleNamespace(
            metadata=SimpleNamespace(name=name, namespace="aqp"),
            spec=SimpleNamespace(
                replicas=replicas,
                template=SimpleNamespace(
                    spec=SimpleNamespace(containers=[SimpleNamespace(image=image)]),
                ),
            ),
            status=SimpleNamespace(
                ready_replicas=ready,
                conditions=[
                    SimpleNamespace(
                        type="Available",
                        status="True",
                        reason="MinimumReplicasAvailable",
                        message="ok",
                    )
                ],
            ),
        )

    def test_running_when_all_replicas_ready(self) -> None:
        dep = self._mock_deployment(replicas=3, ready=3)
        status = _deployment_to_status(dep, provider_alias="kubernetes")
        assert status.phase == DeploymentLifecyclePhase.RUNNING
        assert status.replicas_desired == 3
        assert status.replicas_ready == 3
        assert status.image == "x:1"
        assert len(status.conditions) == 1

    def test_starting_when_no_replicas_ready_yet(self) -> None:
        dep = self._mock_deployment(replicas=2, ready=0)
        status = _deployment_to_status(dep, provider_alias="kubernetes")
        assert status.phase == DeploymentLifecyclePhase.STARTING

    def test_degraded_when_partial_replicas_ready(self) -> None:
        dep = self._mock_deployment(replicas=3, ready=2)
        status = _deployment_to_status(dep, provider_alias="kubernetes")
        assert status.phase == DeploymentLifecyclePhase.DEGRADED

    def test_stopped_when_replicas_zero(self) -> None:
        dep = self._mock_deployment(replicas=0, ready=0)
        status = _deployment_to_status(dep, provider_alias="kubernetes")
        assert status.phase == DeploymentLifecyclePhase.STOPPED


class TestProviderConstructor:
    def test_env_var_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AQP_CP_KUBECONFIG_PATH", "/tmp/kc")
        monkeypatch.setenv("AQP_CP_KUBE_CONTEXT", "test-ctx")
        monkeypatch.setenv("AQP_CP_KUBE_NAMESPACE_DEFAULT", "custom-ns")
        provider = KubernetesProvider()
        assert provider.kubeconfig_path == "/tmp/kc"
        assert provider.kube_context == "test-ctx"
        assert provider.default_namespace == "custom-ns"
