"""Auth surface for the AQP control plane.

Delegates to ``aqp_platform_core.auth`` for the JWT validator and the
RBAC scope grid — see ADR 005. The deps + decorators in this package
adapt those primitives to FastAPI's ``Depends`` interface.
"""
from __future__ import annotations

from aqp_cp.auth.deps import (
    AuthenticatedUser,
    require_auth,
    require_scope,
)
from aqp_cp.auth.validator import (
    get_validator,
    reset_validator,
)

__all__ = [
    "AuthenticatedUser",
    "require_auth",
    "require_scope",
    "get_validator",
    "reset_validator",
]
