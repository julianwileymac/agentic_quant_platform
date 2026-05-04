from __future__ import annotations

import pytest


class StubPolarisClient:
    def __init__(
        self,
        *,
        catalog_present: bool = False,
        principal_present: bool = False,
        principal_role_present: bool = False,
        catalog_role_present: bool = False,
        principal_credentials: dict[str, str] | None = None,
    ) -> None:
        self.catalog_present = catalog_present
        self.principal_present = principal_present
        self.principal_role_present = principal_role_present
        self.catalog_role_present = catalog_role_present
        self.principal_credentials = principal_credentials
        self.calls: list[str] = []

    # OAuth ------------------------------------------------------------
    def oauth_token(self, force: bool = False):  # noqa: ARG002
        self.calls.append("oauth_token")
        from aqp.services.polaris_client import PolarisAuth

        return PolarisAuth(access_token="token")

    # Catalogs ---------------------------------------------------------
    def get_catalog(self, name):  # noqa: ARG002
        self.calls.append(f"get_catalog:{name}")
        return {"name": name} if self.catalog_present else None

    def create_catalog(self, name, **_):  # noqa: ARG002
        self.calls.append(f"create_catalog:{name}")
        self.catalog_present = True
        return {"name": name, "created": True}

    # Principals -------------------------------------------------------
    def get_principal(self, name):  # noqa: ARG002
        self.calls.append(f"get_principal:{name}")
        return {"principal": {"name": name}} if self.principal_present else None

    def create_principal(self, name, **_):
        self.calls.append(f"create_principal:{name}")
        self.principal_present = True
        payload: dict[str, object] = {"principal": {"name": name}}
        if self.principal_credentials:
            payload["credentials"] = dict(self.principal_credentials)
        return payload

    def get_principal_role(self, name):  # noqa: ARG002
        self.calls.append(f"get_principal_role:{name}")
        return {"name": name} if self.principal_role_present else None

    def create_principal_role(self, name):
        self.calls.append(f"create_principal_role:{name}")
        self.principal_role_present = True
        return {"name": name, "created": True}

    def assign_principal_role(self, *, principal, principal_role):
        self.calls.append(f"assign_principal_role:{principal}->{principal_role}")

    def get_catalog_role(self, *, catalog, role):
        self.calls.append(f"get_catalog_role:{catalog}.{role}")
        return {"name": role} if self.catalog_role_present else None

    def create_catalog_role(self, *, catalog, role):
        self.calls.append(f"create_catalog_role:{catalog}.{role}")
        self.catalog_role_present = True
        return {"name": role, "created": True}

    def assign_catalog_role(self, *, catalog, principal_role, catalog_role):
        self.calls.append(f"assign_catalog_role:{principal_role}->{catalog}.{catalog_role}")

    def grant_catalog_privilege(self, *, catalog, catalog_role, privilege):
        self.calls.append(f"grant_catalog_privilege:{catalog}.{catalog_role}.{privilege}")


@pytest.fixture
def manager_factory(monkeypatch, tmp_path):
    from aqp.config import settings as _settings
    from aqp.services import iceberg_bootstrap

    monkeypatch.setattr(_settings, "bootstrap_state_dir", tmp_path, raising=False)
    monkeypatch.setattr(_settings, "iceberg_catalog_warehouse_name", "quickstart_catalog", raising=False)
    monkeypatch.setattr(_settings, "iceberg_principal_name", "aqp_runtime", raising=False)
    monkeypatch.setattr(_settings, "iceberg_principal_role", "aqp_runtime_role", raising=False)
    monkeypatch.setattr(_settings, "iceberg_catalog_role", "aqp_runtime_catalog_role", raising=False)
    monkeypatch.setattr(_settings, "iceberg_catalog_privilege", "CATALOG_MANAGE_CONTENT", raising=False)
    monkeypatch.setattr(_settings, "iceberg_default_base_location", "file:///tmp", raising=False)
    monkeypatch.setattr(_settings, "iceberg_catalog_storage_type", "FILE", raising=False)

    def _factory(stub):
        return iceberg_bootstrap.IcebergBootstrapManager(client=stub)

    return _factory


def test_bootstrap_full_flow_persists_credentials(manager_factory, tmp_path):
    stub = StubPolarisClient(
        principal_credentials={"clientId": "abc123", "clientSecret": "secret"},
    )
    manager = manager_factory(stub)
    report = manager.bootstrap()

    assert report.success is True
    statuses = {step.name: step.status for step in report.steps}
    assert statuses["ensure_catalog"] == "created"
    assert statuses["ensure_principal"] == "created"
    assert statuses["assign_principal_role"] == "ok"
    assert statuses["grant_catalog_privilege"] == "ok"

    creds_file = tmp_path / "polaris-principal.json"
    assert creds_file.exists()
    assert "abc123" in creds_file.read_text()
    assert report.credentials_persisted is True


def test_bootstrap_idempotent_when_everything_exists(manager_factory):
    stub = StubPolarisClient(
        catalog_present=True,
        principal_present=True,
        principal_role_present=True,
        catalog_role_present=True,
    )
    manager = manager_factory(stub)
    report = manager.bootstrap()

    assert report.success is True
    statuses = {step.name: step.status for step in report.steps}
    assert statuses["ensure_catalog"] == "exists"
    assert statuses["ensure_principal"] == "exists"
    assert statuses["ensure_catalog_role"] == "exists"
    # Even when nothing was created we should still have idempotent assigns.
    assert statuses["assign_principal_role"] == "ok"
    assert statuses["grant_catalog_privilege"] == "ok"


def test_status_reports_components(manager_factory):
    stub = StubPolarisClient(
        catalog_present=True,
        principal_present=False,
    )
    manager = manager_factory(stub)
    status = manager.status()

    assert status["catalog_present"] is True
    assert status["principal_present"] is False
    assert status["polaris_reachable"] is True
