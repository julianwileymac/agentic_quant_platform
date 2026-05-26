"""AWS Cognito :class:`IdentityProvider`.

Subclasses :class:`GenericOidcProvider` because Cognito User Pools
expose a standards-compliant OIDC discovery endpoint at
``https://cognito-idp.{region}.amazonaws.com/{user-pool-id}/.well-known/openid-configuration``.

Selection:

- ``settings.auth_provider = "aws_cognito"``
- ``settings.auth_oidc_issuer`` -> the user-pool issuer URL
- ``settings.auth_oidc_audience`` -> the App Client id (Cognito
  encodes it as ``aud`` in id-tokens; access-tokens use
  ``client_id``, so the validator is configured to accept either).

The :class:`IdentityProviderMeta` metaclass auto-registers the
subclass via :func:`aqp.core.registry.register` per AGENTS rule 27.

Single-account-mode role: Cognito is the documented IdP for the
single-account fallback path described in the overhaul blueprint
§4.3 — when no AWS Organization is configured, the operator
provisions a Cognito User Pool in the lone workload account and
points the admin BFF at it. This keeps the admin login flow
working without requiring IAM Identity Center (which itself
requires Org enrollment).
"""
from __future__ import annotations

import logging

from aqp.auth.providers.generic_oidc import GenericOidcProvider

logger = logging.getLogger(__name__)


class AwsCognitoProvider(GenericOidcProvider):
    """AWS Cognito User Pool OIDC provider."""

    provider_kind = "aws_cognito"
    provider_alias = "AwsCognitoProvider"


__all__ = ["AwsCognitoProvider"]
