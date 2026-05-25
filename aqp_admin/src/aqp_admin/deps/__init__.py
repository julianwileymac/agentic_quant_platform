"""FastAPI ``Depends(...)`` factories for the admin BFF.

Modules:

- :mod:`aqp_admin.deps.identity` — Entra-primary bearer validation +
  scope enforcement.
- :mod:`aqp_admin.deps.audit` — audit sink + per-request audit context
  helpers.
"""
from __future__ import annotations

from aqp_admin.audit.sink import reset_audit_sink
from aqp_admin.deps.audit import (
    AuditContext,
    audit_context_dep,
    get_audit_sink,
)
from aqp_admin.deps.identity import (
    AdminUser,
    require_admin,
    require_admin_scope,
    reset_admin_validator,
)

__all__ = [
    "AdminUser",
    "AuditContext",
    "audit_context_dep",
    "get_audit_sink",
    "require_admin",
    "require_admin_scope",
    "reset_admin_validator",
    "reset_audit_sink",
]
