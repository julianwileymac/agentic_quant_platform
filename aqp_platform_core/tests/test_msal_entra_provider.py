"""MsalEntraValidator shim tests — endpoint derivation + token endpoint."""
from __future__ import annotations

from aqp_platform_core.auth.providers.msal_entra import (
    MsalEntraValidator,
    msal_entra_jwt_validator_config,
)


class TestMsalEntraEndpoints:
    def test_token_endpoint_for_organizations(self) -> None:
        validator = MsalEntraValidator(
            tenant="organizations",
            audience="api://aqp-control-plane",
        )
        assert validator.token_endpoint() == (
            "https://login.microsoftonline.com/organizations/oauth2/v2.0/token"
        )

    def test_token_endpoint_for_tenant_uuid(self) -> None:
        validator = MsalEntraValidator(
            tenant="00000000-0000-0000-0000-000000000000",
            audience="api://aqp",
        )
        assert validator.token_endpoint().endswith(
            "/00000000-0000-0000-0000-000000000000/oauth2/v2.0/token"
        )

    def test_jwt_validator_uses_entra_jwks(self) -> None:
        validator = MsalEntraValidator(tenant="organizations", audience="api://aqp")
        jwt_v = validator.jwt_validator()
        assert (
            jwt_v.jwks_url
            == "https://login.microsoftonline.com/organizations/discovery/v2.0/keys"
        )

    def test_helper_config_aligns(self) -> None:
        cfg = msal_entra_jwt_validator_config(
            tenant="common", audience="api://aqp"
        )
        assert cfg.issuer == "https://login.microsoftonline.com/common/v2.0"
        assert (
            cfg.jwks_url_override
            == "https://login.microsoftonline.com/common/discovery/v2.0/keys"
        )


class TestScopeBuilding:
    def test_default_scope_appends_default(self) -> None:
        validator = MsalEntraValidator(
            tenant="organizations", audience="api://aqp-control-plane"
        )
        scope = validator._build_scope("api://aqp-control-plane", ())
        assert scope == "api://aqp-control-plane/.default"

    def test_extra_scopes_appended(self) -> None:
        validator = MsalEntraValidator(
            tenant="organizations", audience="api://aqp-control-plane"
        )
        scope = validator._build_scope(
            "api://aqp-control-plane", ("offline_access",)
        )
        assert scope == "api://aqp-control-plane/.default offline_access"

    def test_audience_already_has_default(self) -> None:
        validator = MsalEntraValidator(
            tenant="organizations", audience="api://aqp/.default"
        )
        scope = validator._build_scope("api://aqp/.default", ())
        assert scope == "api://aqp/.default"
