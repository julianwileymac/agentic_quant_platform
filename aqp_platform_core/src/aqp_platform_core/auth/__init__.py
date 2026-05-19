"""Authentication primitives shared across the AQP planes.

- :mod:`aqp_platform_core.auth.jwt_validator` — JWKS-backed RS256 JWT validator.
- :mod:`aqp_platform_core.auth.claims` — canonical claim namespace constants.
- :mod:`aqp_platform_core.auth.rbac` — four-role scope grid.
- :mod:`aqp_platform_core.auth.resource_filter` — resource-scoped list filter
  enforced by every list endpoint in the control plane.
"""
from __future__ import annotations

from aqp_platform_core.auth.claims import (
    CANONICAL_CLAIMS_NAMESPACE,
    LEGACY_CLAIMS_NAMESPACE,
    claim_key,
    extract_claim,
)
from aqp_platform_core.auth.jwt_validator import (
    JwtValidationError,
    JwtValidator,
    JwtValidatorConfig,
)
from aqp_platform_core.auth.rbac import (
    SCOPE_ADMIN_CLUSTER,
    SCOPE_MANAGE_AGENTS,
    SCOPE_MANAGE_INFRA,
    SCOPE_READ_INFRA,
    ALL_SCOPES,
    ROLE_ADMIN,
    ROLE_OPERATOR,
    ROLE_SUPERADMIN,
    ROLE_VIEWER,
    expand_role,
    role_grants,
)
from aqp_platform_core.auth.resource_filter import (
    filter_resources,
    has_admin_cluster,
    user_resource_ids,
)

__all__ = [
    # claims
    "CANONICAL_CLAIMS_NAMESPACE",
    "LEGACY_CLAIMS_NAMESPACE",
    "claim_key",
    "extract_claim",
    # JWT validator
    "JwtValidationError",
    "JwtValidator",
    "JwtValidatorConfig",
    # RBAC scopes
    "SCOPE_ADMIN_CLUSTER",
    "SCOPE_MANAGE_AGENTS",
    "SCOPE_MANAGE_INFRA",
    "SCOPE_READ_INFRA",
    "ALL_SCOPES",
    # RBAC roles
    "ROLE_ADMIN",
    "ROLE_OPERATOR",
    "ROLE_SUPERADMIN",
    "ROLE_VIEWER",
    "expand_role",
    "role_grants",
    # Resource filter
    "filter_resources",
    "has_admin_cluster",
    "user_resource_ids",
]
