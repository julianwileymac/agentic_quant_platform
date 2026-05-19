"""Phase 5a-c skeleton tests — app factory + health + auth wiring."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aqp_cp.auth.deps import AuthenticatedUser, _payload_to_user, _extract_scopes
from aqp_cp.main import create_app
from aqp_cp.models import (
    DeploymentLifecyclePhase,
    DeploymentSpec,
    DeploymentStatus,
    WorkloadAction,
    WorkloadRun,
    WorkloadRunStatus,
)
from aqp_cp.settings import (
    ControlPlaneSettings,
    get_settings,
    reset_settings_cache,
)


@pytest.fixture(autouse=True)
def _reset_settings() -> None:
    reset_settings_cache()


class TestAppFactory:
    def test_creates_fastapi_with_openapi_at_manage(self) -> None:
        app = create_app()
        assert app.title == "AQP Control Plane"
        assert app.openapi_url == "/manage/openapi.json"

    def test_health_endpoint_responds(self) -> None:
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/manage/health")
            assert response.status_code == 200
            body = response.json()
            assert body["status"] == "ok"
            assert body["data"]["service"] == "aqp-control-plane"
            assert "version" in body["data"]
            assert "provider" in body["data"]
            assert "auth_enabled" in body["data"]

    def test_openapi_spec_renders(self) -> None:
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/manage/openapi.json")
            assert response.status_code == 200
            spec = response.json()
            assert spec["info"]["title"] == "AQP Control Plane"
            assert "/manage/health" in spec["paths"]


class TestAuthDeps:
    def test_extract_scopes_from_oauth_scope_string(self) -> None:
        payload = {"scope": "read:infrastructure manage:agents"}
        scopes = _extract_scopes(payload)
        assert "read:infrastructure" in scopes
        assert "manage:agents" in scopes

    def test_extract_scopes_from_permissions_array(self) -> None:
        payload = {"permissions": ["read:infrastructure", "admin:cluster"]}
        scopes = _extract_scopes(payload)
        assert "admin:cluster" in scopes

    def test_extract_scopes_expands_roles_via_lattice(self) -> None:
        payload = {"https://aqp.internal/roles": ["aqp-admin"]}
        scopes = _extract_scopes(payload)
        assert "read:infrastructure" in scopes
        assert "manage:agents" in scopes
        assert "manage:infrastructure" in scopes
        # admin:cluster is superadmin-only
        assert "admin:cluster" not in scopes

    def test_payload_to_user_populates_fields(self) -> None:
        payload = {
            "sub": "auth0|abc",
            "scope": "read:infrastructure",
            "https://aqp.internal/org_id": "org-1",
            "https://aqp.internal/workspace_id": "ws-1",
            "https://aqp.internal/roles": ["aqp-viewer"],
            "https://aqp.internal/resources": ["res-1", "res-2"],
        }
        user = _payload_to_user(payload)
        assert user.sub == "auth0|abc"
        assert user.org_id == "org-1"
        assert user.workspace_id == "ws-1"
        assert user.roles == ("aqp-viewer",)
        assert user.resources == frozenset({"res-1", "res-2"})
        assert "read:infrastructure" in user.scopes

    def test_authenticated_user_has_scope_respects_admin_cluster(self) -> None:
        user = AuthenticatedUser(
            sub="x",
            payload={},
            scopes=frozenset({"admin:cluster"}),
        )
        assert user.has_scope("manage:agents")
        assert user.has_scope("anything")


class TestModelReExports:
    def test_deployment_spec_roundtrips(self) -> None:
        spec = DeploymentSpec(
            service_id="aqp-api",
            image="ghcr.io/x:dev",
            replicas=2,
        )
        rebuilt = DeploymentSpec.model_validate(spec.model_dump())
        assert rebuilt == spec

    def test_deployment_status_defaults_unknown(self) -> None:
        status = DeploymentStatus(
            service_id="aqp-api",
            provider="docker_compose",
        )
        assert status.phase == DeploymentLifecyclePhase.UNKNOWN

    def test_workload_run_pydantic_strict(self) -> None:
        from datetime import datetime, timezone

        run = WorkloadRun(
            run_id="run-1",
            started_at=datetime.now(timezone.utc),
            action=WorkloadAction.SCALE,
            provider="kubernetes",
            target="aqp-worker",
            user_id="auth0|abc",
        )
        assert run.status == WorkloadRunStatus.PENDING


class TestSettings:
    def test_auth_disabled_when_no_issuer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AQP_AUTH_OIDC_ISSUER", raising=False)
        reset_settings_cache()
        s = get_settings()
        assert s.auth_enabled is False

    def test_auth_enabled_when_required_and_issuer_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AQP_AUTH_OIDC_ISSUER", "https://test.auth0.com/")
        monkeypatch.setenv("AQP_CP_AUTH_REQUIRED", "true")
        reset_settings_cache()
        s = get_settings()
        assert s.auth_enabled is True
        assert s.auth_oidc_issuer == "https://test.auth0.com/"


class TestNoAqpImport:
    """Strict-isolation invariant (ADR 005)."""

    def test_no_aqp_imports_in_aqp_cp_tree(self) -> None:
        import os
        import re
        from pathlib import Path

        src_root = Path(__file__).resolve().parents[1] / "src" / "aqp_cp"
        pattern = re.compile(r"^\s*(?:from|import)\s+aqp(?:\.|$)", re.MULTILINE)
        offenders: list[str] = []
        for path in src_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for match in pattern.finditer(text):
                # Allow imports of aqp_platform_core / aqp_cp itself.
                snippet = match.group(0)
                if "aqp_platform_core" in snippet or "aqp_cp" in snippet:
                    continue
                offenders.append(f"{path.relative_to(src_root.parent.parent)}: {snippet.strip()}")
        assert not offenders, (
            "aqp_control_plane MUST NOT import from aqp.* (ADR 005). Offenders:\n"
            + "\n".join(offenders)
        )
