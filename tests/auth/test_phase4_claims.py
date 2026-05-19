"""Phase 4 tests — claims namespace migration + scope grid + resource filter."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from aqp.api.security import _namespaced_claim, filter_resources_for_user


class TestNamespacedClaim:
    def test_canonical_namespace_wins(self) -> None:
        claims = {
            "https://aqp.internal/org_id": "org-new",
            "https://aqp/org_id": "org-legacy",
        }
        assert _namespaced_claim(claims, "org_id") == "org-new"

    def test_legacy_alias_falls_back(self) -> None:
        claims = {"https://aqp/roles": ["aqp-admin"]}
        assert _namespaced_claim(claims, "roles") == ["aqp-admin"]

    def test_missing_returns_none(self) -> None:
        assert _namespaced_claim({}, "resources") is None

    def test_resources_claim_canonical(self) -> None:
        claims = {"https://aqp.internal/resources": ["r1", "r2"]}
        assert _namespaced_claim(claims, "resources") == ["r1", "r2"]


class TestFilterResourcesForUser:
    def _request_with_claims(self, claims: dict | None):
        req = MagicMock()
        req.state.oidc_claims = claims
        return req

    def test_admin_cluster_sees_everything(self) -> None:
        req = self._request_with_claims({"scope": "admin:cluster"})
        items = [{"id": "a"}, {"id": "b"}]
        assert filter_resources_for_user(items, req) == items

    def test_non_admin_filters_by_resources_claim(self) -> None:
        req = self._request_with_claims(
            {
                "scope": "read:infrastructure",
                "https://aqp.internal/resources": ["a"],
            }
        )
        items = [{"id": "a"}, {"id": "b"}]
        assert [i["id"] for i in filter_resources_for_user(items, req)] == ["a"]

    def test_legacy_namespace_still_honoured(self) -> None:
        req = self._request_with_claims(
            {
                "scope": "read:infrastructure",
                "https://aqp/resources": ["legacy-1"],
            }
        )
        items = [{"id": "legacy-1"}, {"id": "other"}]
        assert [i["id"] for i in filter_resources_for_user(items, req)] == ["legacy-1"]

    def test_no_request_returns_all(self) -> None:
        items = [{"id": "a"}, {"id": "b"}]
        assert filter_resources_for_user(items, None) == items

    def test_no_oidc_claims_returns_all(self) -> None:
        req = self._request_with_claims(None)
        items = [{"id": "a"}]
        assert filter_resources_for_user(items, req) == items


class TestProvisionAuth0Render:
    def test_render_substitutes_placeholders(self) -> None:
        # Skip if cryptography / Auth0 deps aren't present in this env
        try:
            from build.scripts.provision_auth0 import ProvisionSettings, render_action
        except Exception:
            pytest.skip("provision_auth0 module not importable")

        repo_root = Path(__file__).resolve().parents[2]
        template = (
            repo_root
            / "terraform"
            / "modules"
            / "auth0_identity"
            / "post_login_action.js.tftpl"
        )
        if not template.exists():
            pytest.skip("template file missing")

        settings = ProvisionSettings(
            domain="test-tenant.us.auth0.com",
            m2m_client_id="mid",
            m2m_client_secret="msec",
            sync_url="https://api.aqp.example.com/_internal/auth0/sync",
            api_audience="https://api.aqp.internal/manage",
            claims_namespace="https://aqp.internal/",
            action_template_path=template,
            dry_run=True,
        )
        rendered = render_action(settings)
        assert "https://aqp.internal/" in rendered
        assert "https://api.aqp.internal/manage" in rendered
        assert "https://api.aqp.example.com/_internal/auth0/sync" in rendered
        # The $${...} escape sequence in the .tftpl should collapse to ${...}
        # so the rendered JS uses normal interpolation at runtime.
        assert "${tokenResponse.access_token}" in rendered
        assert "${response.status}" in rendered
        # And the .tftpl substitution placeholders should be GONE.
        assert "${claims_namespace}" not in rendered
        assert "${api_audience}" not in rendered
        assert "${sync_url}" not in rendered

    def test_render_emits_namespaced_setcustomclaim_calls(self) -> None:
        try:
            from build.scripts.provision_auth0 import ProvisionSettings, render_action
        except Exception:
            pytest.skip("provision_auth0 module not importable")

        repo_root = Path(__file__).resolve().parents[2]
        template = (
            repo_root
            / "terraform"
            / "modules"
            / "auth0_identity"
            / "post_login_action.js.tftpl"
        )
        if not template.exists():
            pytest.skip("template file missing")

        settings = ProvisionSettings(
            domain="x.auth0.com",
            m2m_client_id="c",
            m2m_client_secret="s",
            sync_url="https://x/sync",
            api_audience="https://aud/",
            claims_namespace="https://ns.test/",
            action_template_path=template,
            dry_run=True,
        )
        rendered = render_action(settings)
        # The setCustomClaim call template should reference the rendered
        # namespace.
        assert "`https://ns.test/${key}`" in rendered
