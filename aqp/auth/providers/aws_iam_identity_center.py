"""AWS IAM Identity Center :class:`IdentityProvider`.

Subclasses :class:`GenericOidcProvider` because IAM Identity Center
(formerly AWS SSO) exposes a standards-compliant OIDC discovery
endpoint at
``https://oidc.{region}.amazonaws.com/.well-known/openid-configuration``
once the Identity Center instance is enabled. The
:class:`IdentityProviderMeta` metaclass auto-registers the subclass
via :func:`aqp.core.registry.register` per AGENTS rule 27 — no manual
``@register`` decorator.

Selection:

- Set ``settings.auth_provider = "aws_iam_identity_center"`` to make
  it the active provider.
- Set ``settings.auth_oidc_issuer = "https://identitycenter.amazonaws.com/ssoins-{instance-id}"``
  (the public discovery URL the Identity Center "External
  identities" pane prints for OIDC consumers).
- ``settings.auth_oidc_audience`` is the resource indicator
  ("application ARN") IAM Identity Center prints for the AQP
  application.

Group sync: IAM Identity Center groups arrive as a top-level
``groups`` claim (a list of canonical group names). The
:func:`aqp.auth.user.provision_user_from_claims` chain reads them
through :data:`CANONICAL_CLAIMS_NAMESPACE` aware lookups, so
:class:`IdpGroupMapping` rows with
``connection_kind="aws_iam_identity_center"`` are sufficient to
roll the right :class:`Membership` entries on first login.
"""
from __future__ import annotations

import logging

from aqp.auth.providers.generic_oidc import GenericOidcProvider

logger = logging.getLogger(__name__)


class AwsIamIdentityCenterProvider(GenericOidcProvider):
    """IAM Identity Center OIDC provider."""

    provider_kind = "aws_iam_identity_center"
    provider_alias = "AwsIamIdentityCenterProvider"

    # IAM Identity Center exposes the standard OIDC token endpoint plus
    # an ``end_session_endpoint`` so RP-initiated logout via the parent
    # GenericOidcProvider works out of the box. No further customisation
    # needed at the protocol layer; group claims are read by the user
    # provisioner via the same canonical namespace lookups every other
    # provider uses.


__all__ = ["AwsIamIdentityCenterProvider"]
