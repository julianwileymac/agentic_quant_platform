"""Canonical AQP scope taxonomy — single source of truth.

This module is the canonical source for every authorization scope used
by the AQP control plane. It extends the four-role ADR 003 lattice from
:mod:`aqp_platform_core.auth.rbac` with AQP-specific scopes (data /
agents / trading / analytics / iceberg / terraform / tenancy) so route
handlers, MCP tools, the Auth0 dashboard, the Terraform Auth0 module
provisioning the resource server, and the auth0-action post-login
sync can all reference one set of strings.

The constants live on the :class:`AQPScope` namespace class. Use them
in route handlers like::

    from aqp.api.security import require_scope
    from aqp.auth.scopes import AQPScope

    @router.post("/iceberg/{tid}/consolidate")
    async def consolidate(
        ...,
        user = Depends(require_scope(AQPScope.ADMIN_ICEBERG)),
    ): ...

and in the AGENTS rule 22 ``DataMCPTool`` registrations like::

    @register_data_mcp_tool
    class WriteIcebergTool(DataMCPTool):
        required_scopes = [AQPScope.WRITE_DATA, AQPScope.ADMIN_ICEBERG]

Scope-string convention
-----------------------
We deliberately keep the existing ADR 003 strings (``data:read``,
``data:write``, ``read:infrastructure``, ``manage:agents``,
``manage:infrastructure``, ``admin:cluster``, ``deploy:run``,
``deploy:halt``, ``scim:write``) so that every Auth0 token issued
before this module landed remains valid. New scopes follow the
``<resource>:<action>`` pattern (``trade:execute``, ``agent:execute``,
``backtest:create``, ``terraform:apply`` …).

Legacy-role drift fix
---------------------
The Auth0 post-login Action emits two flavours of role names today:

- Tenancy-database roles from
  :mod:`aqp.persistence.models_tenancy`:
  ``viewer / editor / admin / owner``.
- Canonical platform roles from
  :mod:`aqp_platform_core.auth.rbac`:
  ``aqp-viewer / aqp-operator / aqp-admin / aqp-superadmin``.

Before this module landed, ``aqp.api.routes.auth0_sync`` only knew
how to expand the ``aqp-*`` flavour, so a user whose only role was
the tenancy-database ``editor`` ended up with an empty ``scopes``
claim. :func:`legacy_role_to_aqp_role` is the canonical translator
that closes that drift.
"""
from __future__ import annotations

from typing import Final, Iterable

# Re-export the ADR 003 four-scope grid + role names so callers only
# have to import from :mod:`aqp.auth.scopes`.
from aqp_platform_core.auth.rbac import (
    ROLE_ADMIN as PLATFORM_ROLE_ADMIN,
    ROLE_OPERATOR as PLATFORM_ROLE_OPERATOR,
    ROLE_SUPERADMIN as PLATFORM_ROLE_SUPERADMIN,
    ROLE_VIEWER as PLATFORM_ROLE_VIEWER,
    SCOPE_ADMIN_CLUSTER,
    SCOPE_MANAGE_AGENTS,
    SCOPE_MANAGE_INFRA,
    SCOPE_READ_INFRA,
    expand_role,
)

# ---------------------------------------------------------------------------
# Canonical AQP scope namespace
# ---------------------------------------------------------------------------


class AQPScope:
    """Canonical AQP scope strings.

    Every scope used by the control plane lives here. Do not hand-write
    a scope string in route code — import it from this class so refactors
    stay grep-able and the Terraform Auth0 module + Auth0 dashboard +
    aqp_docs/docs/concepts/platform/scopes.md stay aligned.
    """

    # --- Data plane ---------------------------------------------------------
    READ_DATA: Final[str] = "data:read"
    WRITE_DATA: Final[str] = "data:write"
    ADMIN_ICEBERG: Final[str] = "admin:iceberg"

    # --- Infrastructure (ADR 003 four-scope grid) ---------------------------
    READ_INFRASTRUCTURE: Final[str] = SCOPE_READ_INFRA
    MANAGE_AGENTS: Final[str] = SCOPE_MANAGE_AGENTS
    MANAGE_INFRASTRUCTURE: Final[str] = SCOPE_MANAGE_INFRA
    ADMIN_CLUSTER: Final[str] = SCOPE_ADMIN_CLUSTER

    # --- Agents -------------------------------------------------------------
    AGENT_VIEW: Final[str] = "agent:view"
    AGENT_EXECUTE: Final[str] = "agent:execute"
    AGENT_TERMINATE: Final[str] = "agent:terminate"

    # --- Trading / portfolio ------------------------------------------------
    TRADE_READ: Final[str] = "trade:read"
    TRADE_EXECUTE: Final[str] = "trade:execute"
    TRADE_LIVE: Final[str] = "trade:live"

    # --- Backtesting --------------------------------------------------------
    BACKTEST_READ: Final[str] = "backtest:read"
    BACKTEST_CREATE: Final[str] = "backtest:create"

    # --- ML / RL / RAG ------------------------------------------------------
    RAG_QUERY: Final[str] = "rag:query"
    READ_TIMESERIES: Final[str] = "read:timeseries"
    ML_WORKBENCH: Final[str] = "ml:workbench"
    RL_TRAIN: Final[str] = "rl:train"

    # --- Deployment lifecycle (ADR 003 + Terraform Auth0 module) ------------
    DEPLOY_RUN: Final[str] = "deploy:run"
    DEPLOY_HALT: Final[str] = "deploy:halt"

    # --- Terraform IaC (rule 42) --------------------------------------------
    TERRAFORM_PLAN: Final[str] = "terraform:plan"
    TERRAFORM_APPLY: Final[str] = "terraform:apply"
    TERRAFORM_DESTROY: Final[str] = "terraform:destroy"
    TERRAFORM_CANCEL: Final[str] = "terraform:cancel"

    # --- WorkloadRuntime (rule 45 — kill-switch fan-out) --------------------
    WORKLOADS_HALT: Final[str] = "workloads:halt"

    # --- Tenancy ------------------------------------------------------------
    TENANCY_INVITE: Final[str] = "tenancy:invite"
    TENANCY_ADMIN: Final[str] = "tenancy:admin"
    SCIM_WRITE: Final[str] = "scim:write"

    # --- Platform admin -----------------------------------------------------
    # The implicit super-scope: any holder of platform:admin satisfies
    # any other scope check. Used very rarely (only the platform-owner
    # super-admin has it).
    PLATFORM_ADMIN: Final[str] = "platform:admin"


# ---------------------------------------------------------------------------
# Frozen registry of every canonical scope
# ---------------------------------------------------------------------------

ALL_AQP_SCOPES: Final[frozenset[str]] = frozenset(
    {
        AQPScope.READ_DATA,
        AQPScope.WRITE_DATA,
        AQPScope.ADMIN_ICEBERG,
        AQPScope.READ_INFRASTRUCTURE,
        AQPScope.MANAGE_AGENTS,
        AQPScope.MANAGE_INFRASTRUCTURE,
        AQPScope.ADMIN_CLUSTER,
        AQPScope.AGENT_VIEW,
        AQPScope.AGENT_EXECUTE,
        AQPScope.AGENT_TERMINATE,
        AQPScope.TRADE_READ,
        AQPScope.TRADE_EXECUTE,
        AQPScope.TRADE_LIVE,
        AQPScope.BACKTEST_READ,
        AQPScope.BACKTEST_CREATE,
        AQPScope.RAG_QUERY,
        AQPScope.READ_TIMESERIES,
        AQPScope.ML_WORKBENCH,
        AQPScope.RL_TRAIN,
        AQPScope.DEPLOY_RUN,
        AQPScope.DEPLOY_HALT,
        AQPScope.TERRAFORM_PLAN,
        AQPScope.TERRAFORM_APPLY,
        AQPScope.TERRAFORM_DESTROY,
        AQPScope.TERRAFORM_CANCEL,
        AQPScope.WORKLOADS_HALT,
        AQPScope.TENANCY_INVITE,
        AQPScope.TENANCY_ADMIN,
        AQPScope.SCIM_WRITE,
        AQPScope.PLATFORM_ADMIN,
    }
)


# ---------------------------------------------------------------------------
# Legacy tenancy role -> canonical AQP role translator
# ---------------------------------------------------------------------------

# The tenancy database in :mod:`aqp.persistence.models_tenancy` uses
# ``viewer / editor / admin / owner``. The canonical platform roles in
# :mod:`aqp_platform_core.auth.rbac` use ``aqp-viewer / aqp-operator /
# aqp-admin / aqp-superadmin``. The post-login Auth0 sync (and any other
# JWT-construction path) needs both flavours so legacy clients keep
# working AND scope expansion produces a non-empty set.
_LEGACY_ROLE_TO_AQP_ROLE: Final[dict[str, str]] = {
    "viewer": PLATFORM_ROLE_VIEWER,
    "editor": PLATFORM_ROLE_OPERATOR,
    "admin": PLATFORM_ROLE_ADMIN,
    "owner": PLATFORM_ROLE_SUPERADMIN,
}


def legacy_role_to_aqp_role(legacy_role: str) -> str | None:
    """Translate a tenancy-database role into the canonical platform role.

    Returns ``None`` for unknown inputs so callers can decide whether to
    pass-through (``aqp-*`` already canonical) or drop the value.
    """
    if not legacy_role:
        return None
    key = str(legacy_role).strip().lower()
    return _LEGACY_ROLE_TO_AQP_ROLE.get(key)


def normalize_role(role: str) -> str | None:
    """Return the canonical ``aqp-*`` role name for any input.

    Accepts both flavours:

    - ``"admin"`` (legacy tenancy) -> ``"aqp-admin"``
    - ``"aqp-admin"`` (canonical) -> ``"aqp-admin"``
    - anything else -> ``None``
    """
    if not role:
        return None
    candidate = str(role).strip()
    if candidate in {
        PLATFORM_ROLE_VIEWER,
        PLATFORM_ROLE_OPERATOR,
        PLATFORM_ROLE_ADMIN,
        PLATFORM_ROLE_SUPERADMIN,
    }:
        return candidate
    return legacy_role_to_aqp_role(candidate)


# ---------------------------------------------------------------------------
# Canonical role -> scope expansion
# ---------------------------------------------------------------------------


def expand_role_canonical(role: str) -> frozenset[str]:
    """Return every scope granted by *role*, accepting both flavours.

    Wraps :func:`aqp_platform_core.auth.rbac.expand_role` with the
    legacy-role translator so the two histories converge at one entry
    point. Unknown roles return the empty frozenset.
    """
    aqp_role = normalize_role(role)
    if aqp_role is None:
        return frozenset()
    return expand_role(aqp_role)


def expand_roles(roles: Iterable[str]) -> frozenset[str]:
    """Union of :func:`expand_role_canonical` over every input role."""
    granted: set[str] = set()
    for role in roles:
        granted.update(expand_role_canonical(role))
    return frozenset(granted)


__all__ = [
    "AQPScope",
    "ALL_AQP_SCOPES",
    "expand_role_canonical",
    "expand_roles",
    "legacy_role_to_aqp_role",
    "normalize_role",
]
