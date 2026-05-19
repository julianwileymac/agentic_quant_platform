"""Cloud-stub providers — verify health probe + structured unavailable errors."""
from __future__ import annotations

import pytest

from aqp_cp.providers.aws import AwsProvider
from aqp_cp.providers.azure import AzureProvider
from aqp_cp.providers.gcp import GcpProvider
from aqp_platform_core.models.deployment import DeploymentSpec
from aqp_platform_core.models.health import HealthStatus
from aqp_platform_core.providers.protocol import InfrastructureProviderUnavailable


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip every cloud credential env var so the probes report unavailable."""
    for key in (
        "AWS_ACCESS_KEY_ID",
        "AWS_PROFILE",
        "AWS_ROLE_ARN",
        "AWS_WEB_IDENTITY_TOKEN_FILE",
        "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
        "AZURE_CLIENT_ID",
        "AZURE_TENANT_ID",
        "AZURE_CLIENT_SECRET",
        "AZURE_USERNAME",
        "AZURE_FEDERATED_TOKEN_FILE",
        "MSI_ENDPOINT",
        "IDENTITY_ENDPOINT",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_CLOUD_PROJECT",
    ):
        monkeypatch.delenv(key, raising=False)


class TestAws:
    async def test_health_unavailable_without_creds(self, clean_env: None) -> None:
        result = await AwsProvider().health()
        assert result.status == HealthStatus.UNAVAILABLE
        assert result.available is False
        assert "credentials" in result.error.lower()

    async def test_health_ok_with_access_key(
        self, monkeypatch: pytest.MonkeyPatch, clean_env: None
    ) -> None:
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIA-test")
        result = await AwsProvider().health()
        # Degraded — credentials present but workload ops not yet impl.
        assert result.status == HealthStatus.DEGRADED

    async def test_start_raises_unavailable(self) -> None:
        provider = AwsProvider()
        with pytest.raises(InfrastructureProviderUnavailable) as exc_info:
            await provider.start(DeploymentSpec(service_id="x", image="y:1"))
        assert "AWS" in str(exc_info.value)
        assert exc_info.value.details["action"] == "start"
        assert exc_info.value.details["cloud"] == "AWS"


class TestAzure:
    async def test_health_unavailable_without_creds(self, clean_env: None) -> None:
        result = await AzureProvider().health()
        assert result.status == HealthStatus.UNAVAILABLE
        assert "credentials" in result.error.lower()

    async def test_health_ok_with_service_principal(
        self, monkeypatch: pytest.MonkeyPatch, clean_env: None
    ) -> None:
        monkeypatch.setenv("AZURE_CLIENT_ID", "c")
        monkeypatch.setenv("AZURE_TENANT_ID", "t")
        monkeypatch.setenv("AZURE_CLIENT_SECRET", "s")
        result = await AzureProvider().health()
        assert result.status == HealthStatus.DEGRADED

    async def test_scale_raises_unavailable(self) -> None:
        with pytest.raises(InfrastructureProviderUnavailable) as exc_info:
            await AzureProvider().scale("x", 3)
        assert exc_info.value.details["cloud"] == "Azure"


class TestGcp:
    async def test_health_unavailable_without_creds(self, clean_env: None) -> None:
        result = await GcpProvider().health()
        assert result.status == HealthStatus.UNAVAILABLE

    async def test_health_ok_with_google_application_credentials(
        self,
        monkeypatch: pytest.MonkeyPatch,
        clean_env: None,
        tmp_path,
    ) -> None:
        creds = tmp_path / "creds.json"
        creds.write_text("{}")
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(creds))
        result = await GcpProvider().health()
        assert result.status == HealthStatus.DEGRADED

    async def test_list_deployments_raises_unavailable(self) -> None:
        with pytest.raises(InfrastructureProviderUnavailable) as exc_info:
            await GcpProvider().list_deployments()
        assert exc_info.value.details["cloud"] == "GCP"
