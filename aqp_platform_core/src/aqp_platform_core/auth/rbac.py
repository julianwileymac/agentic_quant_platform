"""Four-role RBAC scope grid (ADR 003 + canonical AQP extensions).

Roles compose by including every scope of the next-lower role:

| Role                | Scopes                                                       |
| ------------------- | ------------------------------------------------------------ |
| ``aqp-viewer``      | ``read:infrastructure`` + read-only AQP data/agent/trade     |
| ``aqp-operator``    | viewer + ``manage:agents`` + agent execution + RL/ML/backtest |
| ``aqp-admin``       | operator + ``manage:infrastructure`` + ``data:write`` + IaC  |
|                     | (terraform plan/apply/cancel) + iceberg admin + tenancy invite|
| ``aqp-superadmin``  | admin + ``admin:cluster`` + ``terraform:destroy`` + live     |
|                     | trading + SCIM + platform admin (the only role that bypasses |
|                     | :func:`aqp_platform_core.auth.resource_filter.filter_resources`) |

The four ADR 003 scope strings (``read:infrastructure``, ``manage:agents``,
``manage:infrastructure``, ``admin:cluster``) remain the canonical
"infrastructure" lattice. Phase 1 of the AQP control-plane maturation
extended each role with the AQP-specific scopes that the route handlers,
DataMCP tools, and Auth0 dashboard already use today (``data:read``,
``data:write``, ``trade:execute``, ``terraform:apply``, etc.). The full
list of canonical scope strings lives at :mod:`aqp.auth.scopes` (in the
``aqp`` package) — this module remains import-safe for the standalone
``aqp_platform_core`` micro-project so it MUST NOT import from ``aqp``.
"""
from __future__ import annotations

# --- Scopes ----------------------------------------------------------------

# ADR 003 four-scope grid (kept as the canonical infra-lattice constants).
SCOPE_READ_INFRA = "read:infrastructure"
SCOPE_MANAGE_AGENTS = "manage:agents"
SCOPE_MANAGE_INFRA = "manage:infrastructure"
SCOPE_ADMIN_CLUSTER = "admin:cluster"

# AQP-specific canonical scopes (full list lives in aqp.auth.scopes;
# replicated here as locals so this module remains a self-contained
# importable view inside the standalone ``aqp_platform_core`` package).
_SCOPE_DATA_READ = "data:read"
_SCOPE_DATA_WRITE = "data:write"
_SCOPE_ADMIN_ICEBERG = "admin:iceberg"
_SCOPE_AGENT_VIEW = "agent:view"
_SCOPE_AGENT_EXECUTE = "agent:execute"
_SCOPE_AGENT_TERMINATE = "agent:terminate"
_SCOPE_TRADE_READ = "trade:read"
_SCOPE_TRADE_EXECUTE = "trade:execute"
_SCOPE_TRADE_LIVE = "trade:live"
_SCOPE_BACKTEST_READ = "backtest:read"
_SCOPE_BACKTEST_CREATE = "backtest:create"
_SCOPE_RAG_QUERY = "rag:query"
_SCOPE_ML_WORKBENCH = "ml:workbench"
_SCOPE_RL_TRAIN = "rl:train"
_SCOPE_DEPLOY_RUN = "deploy:run"
_SCOPE_DEPLOY_HALT = "deploy:halt"
_SCOPE_TERRAFORM_PLAN = "terraform:plan"
_SCOPE_TERRAFORM_APPLY = "terraform:apply"
_SCOPE_TERRAFORM_DESTROY = "terraform:destroy"
_SCOPE_TERRAFORM_CANCEL = "terraform:cancel"
_SCOPE_WORKLOADS_HALT = "workloads:halt"
_SCOPE_TENANCY_INVITE = "tenancy:invite"
_SCOPE_TENANCY_ADMIN = "tenancy:admin"
_SCOPE_SCIM_WRITE = "scim:write"
_SCOPE_PLATFORM_ADMIN = "platform:admin"

# Backward-compatible alias (Phase 4 callers imported the legacy four-scope
# frozenset from this module). New callers should import ``ALL_AQP_SCOPES``
# from :mod:`aqp.auth.scopes` instead.
ALL_SCOPES: frozenset[str] = frozenset(
    {
        SCOPE_READ_INFRA,
        SCOPE_MANAGE_AGENTS,
        SCOPE_MANAGE_INFRA,
        SCOPE_ADMIN_CLUSTER,
    }
)

# Full canonical scope set surfaced from this module so downstream code
# can iterate without depending on the higher-level ``aqp.auth.scopes``.
ALL_CANONICAL_SCOPES: frozenset[str] = frozenset(
    {
        SCOPE_READ_INFRA,
        SCOPE_MANAGE_AGENTS,
        SCOPE_MANAGE_INFRA,
        SCOPE_ADMIN_CLUSTER,
        _SCOPE_DATA_READ,
        _SCOPE_DATA_WRITE,
        _SCOPE_ADMIN_ICEBERG,
        _SCOPE_AGENT_VIEW,
        _SCOPE_AGENT_EXECUTE,
        _SCOPE_AGENT_TERMINATE,
        _SCOPE_TRADE_READ,
        _SCOPE_TRADE_EXECUTE,
        _SCOPE_TRADE_LIVE,
        _SCOPE_BACKTEST_READ,
        _SCOPE_BACKTEST_CREATE,
        _SCOPE_RAG_QUERY,
        _SCOPE_ML_WORKBENCH,
        _SCOPE_RL_TRAIN,
        _SCOPE_DEPLOY_RUN,
        _SCOPE_DEPLOY_HALT,
        _SCOPE_TERRAFORM_PLAN,
        _SCOPE_TERRAFORM_APPLY,
        _SCOPE_TERRAFORM_DESTROY,
        _SCOPE_TERRAFORM_CANCEL,
        _SCOPE_WORKLOADS_HALT,
        _SCOPE_TENANCY_INVITE,
        _SCOPE_TENANCY_ADMIN,
        _SCOPE_SCIM_WRITE,
        _SCOPE_PLATFORM_ADMIN,
    }
)

# --- Roles ----------------------------------------------------------------

ROLE_VIEWER = "aqp-viewer"
ROLE_OPERATOR = "aqp-operator"
ROLE_ADMIN = "aqp-admin"
ROLE_SUPERADMIN = "aqp-superadmin"

# Scope set granted by each role. Each role's set is a strict superset of
# the previous role's set; cumulative composition is enforced by the test
# suite at ``tests/auth/test_scopes.py``.
_VIEWER_SCOPES: frozenset[str] = frozenset(
    {
        SCOPE_READ_INFRA,
        _SCOPE_DATA_READ,
        _SCOPE_AGENT_VIEW,
        _SCOPE_TRADE_READ,
        _SCOPE_BACKTEST_READ,
        _SCOPE_RAG_QUERY,
    }
)

_OPERATOR_SCOPES: frozenset[str] = _VIEWER_SCOPES | frozenset(
    {
        SCOPE_MANAGE_AGENTS,
        _SCOPE_AGENT_EXECUTE,
        _SCOPE_AGENT_TERMINATE,
        _SCOPE_BACKTEST_CREATE,
        _SCOPE_ML_WORKBENCH,
        _SCOPE_RL_TRAIN,
        _SCOPE_TRADE_EXECUTE,
        _SCOPE_DEPLOY_RUN,
        _SCOPE_DEPLOY_HALT,
        _SCOPE_WORKLOADS_HALT,
    }
)

_ADMIN_SCOPES: frozenset[str] = _OPERATOR_SCOPES | frozenset(
    {
        SCOPE_MANAGE_INFRA,
        _SCOPE_DATA_WRITE,
        _SCOPE_ADMIN_ICEBERG,
        _SCOPE_TERRAFORM_PLAN,
        _SCOPE_TERRAFORM_APPLY,
        _SCOPE_TERRAFORM_CANCEL,
        _SCOPE_TENANCY_INVITE,
    }
)

_SUPERADMIN_SCOPES: frozenset[str] = _ADMIN_SCOPES | frozenset(
    {
        SCOPE_ADMIN_CLUSTER,
        _SCOPE_TERRAFORM_DESTROY,
        _SCOPE_TENANCY_ADMIN,
        _SCOPE_SCIM_WRITE,
        _SCOPE_TRADE_LIVE,
        _SCOPE_PLATFORM_ADMIN,
    }
)

_ROLE_LATTICE: dict[str, frozenset[str]] = {
    ROLE_VIEWER: _VIEWER_SCOPES,
    ROLE_OPERATOR: _OPERATOR_SCOPES,
    ROLE_ADMIN: _ADMIN_SCOPES,
    ROLE_SUPERADMIN: _SUPERADMIN_SCOPES,
}


def expand_role(role: str) -> frozenset[str]:
    """Return the set of scopes implied by ``role``. Unknown -> empty set."""
    return _ROLE_LATTICE.get(role, frozenset())


def role_grants(role: str, scope: str) -> bool:
    """Return ``True`` if ``role`` implies ``scope``."""
    return scope in expand_role(role)


__all__ = [
    "SCOPE_READ_INFRA",
    "SCOPE_MANAGE_AGENTS",
    "SCOPE_MANAGE_INFRA",
    "SCOPE_ADMIN_CLUSTER",
    "ALL_SCOPES",
    "ALL_CANONICAL_SCOPES",
    "ROLE_VIEWER",
    "ROLE_OPERATOR",
    "ROLE_ADMIN",
    "ROLE_SUPERADMIN",
    "expand_role",
    "role_grants",
]
